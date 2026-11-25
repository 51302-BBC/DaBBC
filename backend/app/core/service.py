import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from psycopg.errors import UniqueViolation

from app.database import get_db
from . import repository as repo
from .mail import MailUnavailable, SMTPMailer
from .model import EmployeeCreate
from .policy import (
    TASK_TRANSITION_POLICIES,
    can_assign,
    can_cancel_task,
    can_manage_task,
    can_reopen_task,
    can_update_task_status,
    can_view_task,
    has_role,
)
from .security import hash_password, token_digest, verify_password

SESSION_COOKIE = "office_session"
SESSION_MAX_AGE = 12 * 60 * 60
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
PRIVATE_EMPLOYEE_FIELDS = {"phone", "address", "emergency_contact", "started_on", "inactive_on", "email", "roles"}
TASK_CANCEL_POLICY = "TASK_CANCEL_POLICY"
TASK_REOPEN_POLICY = "TASK_REOPEN_POLICY"


def require_role(actor, *roles):
    if not has_role(actor, *roles):
        raise HTTPException(403, "你沒有執行此操作的權限")


def find(item, message="找不到這筆資料"):
    if item is None:
        raise HTTPException(404, message)
    return item


def validated_patch(payload, nullable=()):
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None and key not in nullable for key, value in changes.items()):
        raise HTTPException(422, "必填欄位不可清空")
    return changes


def bootstrap(conn):
    for setting in (TASK_CANCEL_POLICY, TASK_REOPEN_POLICY):
        if (value := os.getenv(setting)) and value not in TASK_TRANSITION_POLICIES:
            raise ValueError(f"{setting} must be owner, creator, assignee, or unset")
    repo.manager_hierarchy_lock(conn)
    repo.setup(conn)
    email = os.environ.get("BOOTSTRAP_OWNER_EMAIL")
    password = os.environ.get("BOOTSTRAP_OWNER_PASSWORD")
    if not email and not password:
        return
    if not email or not password or not 12 <= len(password) <= 128:
        raise ValueError("Owner bootstrap requires an email and a 12–128 character password")
    bootstrap_owner = EmployeeCreate(name=os.getenv("BOOTSTRAP_OWNER_NAME", "事務所管理員"), email=email)
    if not repo.get_employee_by_email(conn, bootstrap_owner.email):
        if not conn.execute("SELECT 1 FROM employees WHERE active AND 'owner'=ANY(roles)").fetchone():
            repo.insert(conn, "employees", {
                "name": bootstrap_owner.name,
                "email": bootstrap_owner.email,
                "password_hash": hash_password(password),
                "roles": ["owner"],
            })


def current_user(request: Request, conn=Depends(get_db)):
    raw_token = request.cookies.get(SESSION_COOKIE)
    employee = repo.get_session_employee(conn, token_digest(raw_token)) if raw_token else None
    if not employee:
        raise HTTPException(401, "請登入後再繼續")
    return employee


def login(conn, email, password):
    employee = repo.get_employee_by_email(conn, email, lock=True)
    stored = (employee and employee["password_hash"]) or _DUMMY_HASH
    valid = verify_password(password, stored)
    if not employee or not employee["active"] or not employee["password_hash"] or not valid:
        raise HTTPException(401, "電子郵件或密碼不正確")
    token = secrets.token_urlsafe(32)
    repo.create_session(conn, employee["id"], token_digest(token))
    employee.pop("password_hash")
    return token, employee


def logout(conn, raw_token):
    if raw_token:
        repo.delete_session(conn, token_digest(raw_token))


def send_account_link(conn, employee, purpose):
    token = secrets.token_urlsafe(32)
    valid_hours = 48 if purpose == "activate" else 1
    repo.issue_token(conn, employee["id"], purpose, token_digest(token), valid_hours)
    try:
        SMTPMailer().send_link(
            employee, purpose, "啟用事務所帳號" if purpose == "activate" else "重設事務所帳號密碼", token
        )
    except MailUnavailable as error:
        raise HTTPException(503, str(error)) from error


def recover(conn, email):
    if not os.environ.get("SMTP_HOST"):
        raise HTTPException(503, "目前尚未設定寄信服務")
    employee = repo.get_employee_by_email(conn, email, lock=True)
    if employee and employee["active"] and employee["password_hash"]:
        try:
            with conn.transaction():
                send_account_link(conn, employee, "reset")
        except HTTPException:
            # Respond uniformly even when the address does not have an account.
            return


def set_password(conn, token, password, purpose):
    digest = token_digest(token)
    token_row = repo.get_token_employee(conn, digest, purpose)
    if not token_row:
        raise HTTPException(422, "連結已失效。請重新申請連結。")
    employee = repo.get_employee(conn, token_row["employee_id"], lock=True)
    if not employee or not employee["active"] or not repo.consume_token(conn, digest, purpose):
        raise HTTPException(422, "連結已失效。請重新申請連結。")
    repo.patch(conn, "employees", employee["id"], {"password_hash": hash_password(password)})
    repo.revoke_credentials(conn, employee["id"])


def employee_view(actor, employee):
    if has_role(actor, "owner", "admin") or employee["id"] == actor["id"]:
        return employee
    return {key: value for key, value in employee.items() if key not in PRIVATE_EMPLOYEE_FIELDS}


def employees(conn, actor):
    rows = repo.get_employees(conn)
    if has_role(actor, "owner", "admin"):
        return rows
    return [
        employee_view(actor, row) for row in rows
        if row["id"] == actor["id"]
        or has_role(actor, "manager") and row["supervisor_id"] == actor["id"]
    ]


def validate_supervisor(conn, proposed_id, employee_id=None):
    supervisor_id = proposed_id
    seen = {employee_id}
    while supervisor_id is not None:
        if supervisor_id in seen:
            raise HTTPException(422, "直屬主管關係不能形成循環")
        seen.add(supervisor_id)
        supervisor = find(repo.get_employee(conn, supervisor_id), "找不到直屬主管")
        if supervisor_id == proposed_id and (
            not supervisor["active"] or not has_role(supervisor, "owner", "manager")
        ):
            raise HTTPException(422, "請選擇啟用且具主管權限的人員")
        supervisor_id = supervisor["supervisor_id"]


def create_employee(conn, actor, payload):
    require_role(actor, "owner", "admin")
    repo.manager_hierarchy_lock(conn)
    values = payload.model_dump(exclude={"roles"})
    if payload.roles is not None:
        require_role(actor, "owner")
        values["roles"] = sorted(set(payload.roles))
    validate_supervisor(conn, values["supervisor_id"])
    try:
        new_id = repo.insert(conn, "employees", values)
    except UniqueViolation as error:
        raise HTTPException(409, "此電子郵件已有帳號") from error
    employee = repo.get_employee(conn, new_id)
    send_account_link(conn, employee, "activate")
    return employee


def invite_employee(conn, actor, employee_id):
    require_role(actor, "owner", "admin")
    employee = find(repo.get_employee(conn, employee_id, lock=True), "找不到員工")
    if has_role(employee, "owner"):
        require_role(actor, "owner")
    if not employee["active"]:
        raise HTTPException(422, "請先啟用員工帳號")
    stored = repo.get_employee_by_email(conn, employee["email"])
    if stored["password_hash"]:
        raise HTTPException(409, "此帳號已設定密碼，請使用忘記密碼")
    send_account_link(conn, employee, "activate")


def patch_employee(conn, actor, employee_id, payload):
    changes = validated_patch(payload, nullable={"supervisor_id", "started_on", "phone", "address", "emergency_contact"})
    require_role(actor, "owner", "admin")
    repo.manager_hierarchy_lock(conn)
    employee = find(repo.get_employee(conn, employee_id, lock=True), "找不到員工")
    if "roles" in changes or has_role(employee, "owner") or (
        has_role(employee, "admin") and any(key in changes and changes[key] != employee[key] for key in ("email", "active"))
    ):
        require_role(actor, "owner")
    if "roles" in changes:
        if not changes["roles"]:
            raise HTTPException(422, "員工至少需要一個角色")
        changes["roles"] = sorted(set(changes["roles"]))
    if has_role(employee, "owner") and (
        not changes.get("active", employee["active"]) or "owner" not in changes.get("roles", employee["roles"])
    ):
        other_owner = conn.execute(
            "SELECT 1 FROM employees WHERE id<>%s AND active AND 'owner'=ANY(roles) LIMIT 1",
            (employee_id,),
        ).fetchone()
        if not other_owner:
            raise HTTPException(409, "事務所需保留至少一個啟用的老闆帳號")
    if "supervisor_id" in changes:
        validate_supervisor(conn, changes["supervisor_id"], employee_id)
    if changes.get("active", employee["active"]) != employee["active"]:
        changes["inactive_on"] = None if changes["active"] else datetime.now(ZoneInfo("Asia/Taipei")).date()
    email_changed = "email" in changes and changes["email"] != employee["email"]
    try:
        repo.patch(conn, "employees", employee_id, changes)
    except UniqueViolation as error:
        raise HTTPException(409, "此電子郵件已有帳號") from error
    if email_changed or changes.get("active") is False:
        repo.revoke_credentials(conn, employee_id)
    if changes.get("supervisor_id", employee["supervisor_id"]) != employee["supervisor_id"]:
        from app.workflows.service import reroute_for_employee
        reroute_for_employee(conn, employee_id)
    review_roles = {"owner", "admin", "manager"}
    lost_review_role = bool((set(employee["roles"]) & review_roles) - set(changes.get("roles", employee["roles"])))
    if changes.get("active") is False or lost_review_role:
        from app.workflows.service import reroute_for_reviewer
        reroute_for_reviewer(conn, employee_id)
    return repo.get_employee(conn, employee_id)


def handoff(conn, actor, employee_id):
    from app.workflows.repository import Repository
    from app.workflows.service import request_list

    require_role(actor, "owner", "admin")
    employee = find(repo.get_employee(conn, employee_id), "找不到員工")
    pending = request_list(Repository(conn), employee, "review")
    handoff = repo.employee_handoff(conn, employee_id)
    handoff["requests"] = [
        {key: item[key] for key in ("id", "kind", "status")}
        for item in pending if item["reviewer_id"] == employee_id
    ]
    return handoff


def clients(conn, actor):
    visible_tasks = {task["client_id"] for task in tasks(conn, actor)}
    direct_reports = {
        row["id"] for row in repo.get_employees(conn) if row["supervisor_id"] == actor["id"] and row["active"]
    } if has_role(actor, "manager") else set()
    return [
        row for row in repo.get_clients(conn)
        if has_role(actor, "owner", "admin")
        or actor["id"] in row["assignee_ids"]
        or bool(direct_reports.intersection(row["assignee_ids"]))
        or row["id"] in visible_tasks
    ]


def validated_assignees(conn, ids):
    result = sorted(set(ids))
    for employee_id in result:
        if not find(repo.get_employee(conn, employee_id, lock=True), "找不到指定的員工")["active"]:
            raise HTTPException(422, "只能新增啟用中的客戶負責人")
    return result


def create_client(conn, actor, payload):
    require_role(actor, "owner", "admin")
    assignees = validated_assignees(conn, payload.assignee_ids)
    client_id = repo.insert(conn, "clients", {"name": payload.name, "active": payload.active})
    repo.set_client_assignees(conn, client_id, assignees)
    return repo.get_client(conn, client_id)


def patch_client(conn, actor, client_id, payload):
    require_role(actor, "owner", "admin")
    find(repo.lock_client(conn, client_id), "找不到客戶公司")
    changes = validated_patch(payload)
    if "assignee_ids" in changes:
        previous = repo.get_client(conn, client_id)
        assignees = changes.pop("assignee_ids")
        added = set(assignees) - set(previous["assignee_ids"])
        validated_assignees(conn, added)
        repo.set_client_assignees(conn, client_id, sorted(set(assignees)))
    repo.patch(conn, "clients", client_id, changes)
    return repo.get_client(conn, client_id)


def tasks(conn, actor):
    return [task_view(actor, task) for task in repo.get_tasks(conn) if can_view_task(actor, task)]


def task_view(actor, task):
    return {
        **task,
        "can_cancel": can_cancel_task(actor, task, os.getenv(TASK_CANCEL_POLICY)),
        "can_reopen": can_reopen_task(actor, task, os.getenv(TASK_REOPEN_POLICY)),
    }


def task_for_actor(conn, actor, task_id, *, lock=False):
    task = find(repo.get_task(conn, task_id, lock=lock), "找不到任務")
    if not can_view_task(actor, task):
        raise HTTPException(404, "找不到任務")
    return task_view(actor, task)


def check_assignment(conn, actor, client_id, assignee_id, *, require_active_client=True):
    find(repo.lock_client(conn, client_id), "找不到客戶公司")
    client = repo.get_client(conn, client_id)
    assignee = find(repo.get_employee(conn, assignee_id, lock=True), "找不到任務負責人")
    if require_active_client and not client["active"]:
        raise HTTPException(422, "停用的客戶公司無法新增任務")
    if not can_assign(actor, assignee, set(client["assignee_ids"])):
        raise HTTPException(403, "請選擇你可分派的客戶公司負責人")


def create_task(conn, actor, payload):
    require_role(actor, "owner", "manager", "admin")
    check_assignment(conn, actor, payload.client_id, payload.assignee_id)
    task_id = repo.insert(conn, "tasks", {**payload.model_dump(), "created_by": actor["id"]})
    repo.log_task(conn, task_id, actor["id"], "created", {"assignee_id": payload.assignee_id})
    repo.notify(conn, payload.assignee_id, f"新任務：{payload.title}")
    return task_view(actor, repo.get_task(conn, task_id))


def patch_task(conn, actor, task_id, payload):
    task = task_for_actor(conn, actor, task_id, lock=True)
    changes = validated_patch(payload, nullable={"due_on"})
    changes = {key: value for key, value in changes.items() if task[key] != value}
    if not changes:
        return task
    if set(changes) - {"status"} and not can_manage_task(actor, task):
        raise HTTPException(403, "你沒有編輯或改派此任務的權限")
    if "status" in changes:
        status = changes["status"]
        allowed = (
            can_update_task_status(actor, task, status)
            or status == "canceled" and task["can_cancel"]
            or status == "pending" and task["can_reopen"]
        )
        if not allowed:
            raise HTTPException(403, "無法變更此任務的狀態")
    if "assignee_id" in changes:
        check_assignment(conn, actor, task["client_id"], changes["assignee_id"], require_active_client=False)
        repo.log_task(conn, task_id, actor["id"], "reassigned", {
            "from": task["assignee_id"], "to": changes["assignee_id"],
        })
        title = changes.get("title", task["title"])
        repo.notify(conn, changes["assignee_id"], f"任務已分派給你：{title}")
        repo.notify(conn, task["assignee_id"], f"任務已改派：{title}")
    if "status" in changes:
        repo.log_task(conn, task_id, actor["id"], "status", {
            "from": task["status"], "to": changes["status"],
        })
    repo.patch(conn, "tasks", task_id, changes)
    return task_view(actor, repo.get_task(conn, task_id))
