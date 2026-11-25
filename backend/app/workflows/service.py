import base64
import binascii
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import PurePath

from fastapi import HTTPException

from app.core.repository import notify
from app.core.service import clients as visible_clients
from app.holiday_reference import holiday_events

from .model import (
    ADMIN_KINDS,
    KIND_LABELS,
    KINDS,
    SUPERVISOR_KINDS,
    TAIPEI,
    aware,
    dates_between,
    duration,
    today,
)
from .repository import Repository, bootstrap


def fail(status, message):
    raise HTTPException(status, message)


def has_roles(user, *roles):
    return bool(set(user["roles"]) & set(roles))


def require_roles(user, *roles):
    if not has_roles(user, *roles):
        fail(403, "你沒有執行此操作的權限。")


def shared_admin_review():
    return os.environ.get("ADMIN_REVIEW_ROUTING") == "shared"


def route_supervisor(repo, employee):
    supervisor_id = employee["supervisor_id"]
    for delegate in repo.delegates(today()):
        if (delegate["supervisor_id"] == supervisor_id and delegate["active"]
                and has_roles(delegate, "manager", "owner") and delegate["reviewer_id"] != employee["id"]):
            return delegate["reviewer_id"]
    supervisor = repo.employee(supervisor_id) if supervisor_id is not None else None
    if supervisor and supervisor["id"] != employee["id"] and supervisor["active"] and has_roles(supervisor, "manager", "owner"):
        return supervisor["id"]
    return None


def notify_reviewers(repo, row):
    message = f"有一筆新的待審{KIND_LABELS[row['kind']]}申請。"
    if row["reviewer_id"] is not None:
        notify(repo.conn, row["reviewer_id"], message)
    elif row["kind"] in ADMIN_KINDS and shared_admin_review():
        admins = repo.all("SELECT id FROM employees WHERE active AND 'admin'=ANY(roles) AND id<>%s", (row["employee_id"],))
        for admin in admins:
            notify(repo.conn, admin["id"], message)
    else:
        owners = repo.all("SELECT id FROM employees WHERE active AND 'owner'=ANY(roles) AND id<>%s", (row["employee_id"],))
        for owner in owners:
            notify(repo.conn, owner["id"], f"有一筆待指派的{KIND_LABELS[row['kind']]}申請。")


def refresh_assignment(repo, row, employee):
    if row["status"] != "pending" or row["kind"] not in SUPERVISOR_KINDS:
        return row
    manual = repo.employee(row["reviewer_id"]) if row["manually_assigned"] and row["reviewer_id"] else None
    if manual and manual["active"] and has_roles(manual, "manager", "owner") and manual["id"] != employee["id"]:
        return row
    reviewer = route_supervisor(repo, employee)
    if reviewer == row["reviewer_id"] and not row["manually_assigned"]:
        return row
    updated = repo.set_reviewer(row["id"], reviewer)
    repo.add_history(row["id"], None, "rerouted", "依目前直屬主管與代理期間更新審核人。")
    notify_reviewers(repo, updated)
    return updated


def reroute_for_employee(conn, employee_id):
    repo = Repository(conn)
    employee = repo.lock_employee(employee_id)
    if not employee:
        return
    for row in repo.all(
        """SELECT * FROM wf_requests WHERE employee_id=%s AND status='pending'
           ORDER BY id FOR UPDATE""",
        (employee_id,),
    ):
        if row["manually_assigned"] and row["kind"] in SUPERVISOR_KINDS:
            row = repo.set_reviewer(row["id"], None)
            repo.add_history(row["id"], None, "rerouted", "直屬主管異動。")
        refresh_assignment(repo, row, employee)


def reroute_for_reviewer(conn, reviewer_id):
    repo = Repository(conn)
    candidates = repo.all(
        "SELECT id,employee_id FROM wf_requests WHERE reviewer_id=%s AND status='pending' ORDER BY employee_id,id",
        (reviewer_id,),
    )
    for candidate in candidates:
        employee = repo.lock_employee(candidate["employee_id"])
        row = repo.request(candidate["id"], lock=True)
        if row["status"] != "pending" or row["reviewer_id"] != reviewer_id:
            continue
        if row["kind"] in SUPERVISOR_KINDS:
            refresh_assignment(repo, row, employee)
        else:
            updated = repo.set_reviewer(row["id"], None)
            repo.add_history(row["id"], None, "rerouted", "原審核人已停用。")
            notify_reviewers(repo, updated)


def schedule_view(repo):
    value = repo.schedule()
    return {**value, "configured": True} if value else {
        "weekdays": [], "start_time": None, "end_time": None, "break_minutes": 0, "configured": False,
    }


def set_schedule(repo, user, value):
    require_roles(user, "owner", "admin")
    if (not value.weekdays or any(i not in range(7) for i in value.weekdays)
            or len(set(value.weekdays)) != len(value.weekdays)):
        fail(422, "請選擇有效的工作日。")
    if value.start_time.tzinfo is not None or value.end_time.tzinfo is not None:
        fail(422, "班表請輸入臺灣本地時間。")
    span = duration(datetime.combine(date.min, value.start_time), datetime.combine(date.min, value.end_time))
    if not 0 < span or value.break_minutes >= span:
        fail(422, "下班須晚於上班，休息時間須少於班表時段。")
    return {**repo.put_schedule(value), "configured": True}


def add_calendar_event(repo, user, value):
    require_roles(user, "owner", "admin")
    if value.category not in {"holiday", "meeting"}:
        fail(422, "行事曆可登記假期或會議。")
    if value.category != "holiday" and value.workday_override is not None:
        fail(422, "只有假期項目可調整當日是否出勤。")
    title = value.title.strip()
    if not title:
        fail(422, "請填寫行事曆事件名稱。")
    return repo.insert_event(value.model_copy(update={"title": title}))


def calendar(repo, start, end):
    entries = repo.events(start, end)
    registered = {(entry["date"], entry["title"]) for entry in entries}
    entries.extend(
        entry for entry in holiday_events(start, end) if (entry["date"], entry["title"]) not in registered
    )
    rows = repo.all(
        """SELECT r.id,r.kind,r.details,e.name FROM wf_requests r JOIN employees e ON e.id=r.employee_id
           WHERE r.status='approved' AND r.original_id IS NULL AND r.kind IN ('leave','outing')
           AND (r.details->>'start_at')::timestamptz < %s
           AND (r.details->>'end_at')::timestamptz > %s ORDER BY r.id""",
        (datetime.combine(end + timedelta(days=1), time.min, TAIPEI), datetime.combine(start,time.min,TAIPEI)),
    )
    for row in rows:
        begin = aware(row["details"]["start_at"])
        finish = aware(row["details"]["end_at"])
        last_day = (finish - timedelta(microseconds=1)).date()
        entries.append({
            "id": -row["id"], "date": max(begin.date(), start), "end_date": min(last_day, end),
            "category": "personnel", "title": f"{row['name']}｜{KIND_LABELS[row['kind']]}",
            "start_at": begin, "end_at": finish,
        })
    return sorted(entries, key=lambda entry: (entry["date"], entry["category"], entry["title"]))


def configured_workdays(repo, start, end):
    config = repo.schedule()
    overrides = {
        item["date"]: item["workday_override"] for item in repo.events(start, end)
        if item["workday_override"] is not None
    }
    result = {}
    for day in dates_between(start, end):
        result[day] = overrides.get(day, day.weekday() in config["weekdays"] if config else None)
    return config, result


def attendance(repo, employee_id, start, end, configuration=None):
    _, workdays = configuration or configured_workdays(repo, start, end)
    clocks = defaultdict(dict)
    for item in repo.clock_events(employee_id, start, end):
        record = clocks[item["date"]]
        stamp = item["recorded_at"].astimezone(TAIPEI)
        record["clock_" + item["direction"]] = stamp
        if item["correction_id"] is None:
            record["original_clock_" + item["direction"]] = stamp
    result = []
    for day, expected in workdays.items():
        record = clocks[day]
        in_at = record.get("clock_in")
        out_at = record.get("clock_out")
        actual = duration(in_at, out_at) if in_at and out_at else None
        status = (
            "complete" if in_at and out_at else
            "missing_punch" if (in_at or out_at) and day < today() else
            "in_progress" if in_at or out_at else
            "no_record" if expected and day < today() else
            "off" if expected is False else "unrecorded"
        )
        result.append({
            "employee_id": employee_id, "date": day, "clock_in": in_at, "clock_out": out_at,
            "original_clock_in": record.get("original_clock_in"),
            "original_clock_out": record.get("original_clock_out"), "worked_minutes": actual,
            "status": status, "expected_workday": expected,
        })
    return result


def punch(repo, user, action):
    if action not in {"in", "out"}:
        fail(422, "請選擇上班或下班打卡。")
    now = datetime.now(TAIPEI)
    current = now.date()
    if not repo.lock_employee(user["id"])["active"]:
        fail(403, "帳號已停用。")
    existing = repo.clock_events(user["id"], current, current)
    if any(row["direction"] == action for row in existing):
        fail(409, "這個時段已有打卡或補正紀錄。")
    if action == "in" and any(row["direction"] == "out" and row["recorded_at"] < now for row in existing):
        fail(409, "已有較早的下班紀錄。請使用補打卡流程。")
    repo.insert_clock(user["id"], current, action, now)
    return attendance(repo, user["id"], current, current)[0]


def normalize_request(repo, employee, kind, details):
    if kind not in KINDS:
        fail(422, "請選擇有效的申請類型。")
    receipt = None
    try:
        if kind in SUPERVISOR_KINDS:
            start = aware(details["start_at"])
            end = aware(details["end_at"])
            span = duration(start, end)
            minutes = int(details.get("minutes") or span)
            if not 0 < minutes <= span or span > 366 * 24 * 60:
                raise ValueError
            result = {"start_at": start.isoformat(), "end_at": end.isoformat(),
                      "minutes": minutes, "reason": str(details.get("reason") or "").strip()}
            if kind == "leave":
                type_id = int(details["leave_type_id"])
                if not repo.leave_type(type_id):
                    fail(422, "找不到選取的假別。")
                result["leave_type_id"] = type_id
        elif kind == "clock_correction":
            day = date.fromisoformat(details["date"])
            corrected = aware(details["corrected_at"])
            if (details["direction"] not in {"in", "out"} or corrected.date() != day
                    or corrected > datetime.now(TAIPEI)):
                raise ValueError
            result = {"date": day.isoformat(), "direction": details["direction"],
                      "corrected_at": corrected.isoformat(), "reason": str(details.get("reason") or "").strip()}
        elif kind == "expense":
            amount = Decimal(str(details["amount"]))
            purpose = details["purpose"].strip()
            if not amount.is_finite() or not 0 < amount <= 99_999_999 or not purpose:
                raise ValueError
            result = {"date": date.fromisoformat(details["date"]).isoformat(),
                      "amount": str(amount), "purpose": purpose}
            if details.get("client_id"):
                client_id = int(details["client_id"])
                if not any(
                    client["id"] == client_id and client["active"]
                    for client in visible_clients(repo.conn, employee)
                ):
                    fail(422, "找不到所選的客戶公司。")
                result["client_id"] = client_id
            attachment = details.get("attachment_data")
            if attachment:
                name = PurePath(str(details.get("attachment_name") or "")).name
                if not name or len(name) > 180 or len(attachment) > 7_000_000:
                    fail(422, "憑證名稱有誤，或檔案超過 5 MB。")
                content = base64.b64decode(attachment, validate=True)
                if not content or len(content) > 5_000_000:
                    fail(422, "憑證檔案須介於 1 位元組與 5 MB。")
                result["attachment_name"] = name
                receipt = name, content
        else:
            result = {key: value.strip() for key, value in details.items()
                      if key in {"phone", "address", "emergency_contact"} and isinstance(value, str)}
            if not result or any(len(value) > 500 for value in result.values()):
                raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation, binascii.Error, OverflowError):
        fail(422, "申請內容有誤，請核對必填欄位、日期與時數。")
    for key in ("purpose", "reason"):
        if len(result.get(key, "")) > 2000:
            fail(422, "事由或用途最多可輸入 2,000 字。")
    return result, receipt


def confirm_leave_balance(repo, employee_id, kind, details, exclude=None):
    if kind != "leave":
        return
    type_id = details["leave_type_id"]
    if not repo.leave_type(type_id)["requires_balance"]:
        return
    balance = repo.balance(employee_id, type_id)
    used = repo.leave_used(employee_id, type_id, exclude)
    if not balance or balance["total_minutes"] - used["reserved"] - used["used"] < details["minutes"]:
        fail(409, "這個假別的剩餘時數不足。")


def submit(repo, user, value):
    employee = repo.lock_employee(user["id"])
    if not employee["active"]:
        fail(403, "帳號已停用。")
    details, receipt = normalize_request(repo, employee, value.kind, value.details)
    confirm_leave_balance(repo, user["id"], value.kind, details)
    reviewer = route_supervisor(repo, employee) if value.kind in SUPERVISOR_KINDS else None
    row = repo.insert_request(user["id"], value.kind, reviewer, details)
    if receipt:
        repo.put_receipt(row["id"], *receipt)
    repo.add_history(row["id"], user["id"], "submitted")
    notify_reviewers(repo, row)
    return view_request(repo, row, user["name"])


def can_review(user, row):
    if user["id"] == row["employee_id"]:
        return False
    assigned = row["reviewer_id"]
    if row["kind"] in SUPERVISOR_KINDS:
        return has_roles(user, "manager", "owner") and assigned == user["id"]
    return has_roles(user, "admin") and (
        assigned == user["id"] or assigned is None and shared_admin_review()
    )


def effective_reviewer(repo, row, employee):
    if row["kind"] not in SUPERVISOR_KINDS or row["status"] != "pending":
        return row["reviewer_id"]
    manual = repo.employee(row["reviewer_id"]) if row["manually_assigned"] and row["reviewer_id"] else None
    if manual and manual["active"] and has_roles(manual, "manager", "owner"):
        return manual["id"]
    return route_supervisor(repo, employee)


def view_request(repo, row, employee_name, history=None):
    return {
        **{field: row[field] for field in (
            "id", "kind", "status", "employee_id", "reviewer_id", "details", "created_at", "original_id"
        )},
        "employee_name": employee_name,
        "history": repo.history([row["id"]]) if history is None else history,
    }


def request_list(repo, user, scope):
    if scope not in {"mine", "review", "unassigned", "all"}:
        fail(422, "請選擇有效的申請檢視。")
    if scope == "unassigned":
        require_roles(user, "owner")
    visible = []
    employees = {}
    admins = set()
    if scope == "unassigned" and shared_admin_review():
        admins = {row["id"] for row in repo.all("SELECT id FROM employees WHERE active AND 'admin'=ANY(roles)")}
    for row in repo.requests():
        own = row["employee_id"] == user["id"]
        if scope == "mine" and not own:
            continue
        if row["kind"] in SUPERVISOR_KINDS and row["status"] == "pending":
            if row["employee_id"] not in employees:
                employees[row["employee_id"]] = repo.employee(row["employee_id"])
            actual = effective_reviewer(repo, row, employees[row["employee_id"]])
            row = {**row, "reviewer_id": actual}
        queue = can_review(user, row)
        if scope == "review" and (not queue or row["status"] != "pending"):
            continue
        if scope == "unassigned":
            blocked_admin = row["kind"] in ADMIN_KINDS and (
                not admins - {row["employee_id"]}
            )
            if row["status"] != "pending" or row["reviewer_id"] is not None or (
                row["kind"] in ADMIN_KINDS and not blocked_admin
            ):
                continue
        if scope == "all" and not (
            own or queue or has_roles(user, "owner")
            or row["kind"] in ADMIN_KINDS and has_roles(user, "admin")
            and (shared_admin_review() or row["reviewer_id"] == user["id"])
            or row["kind"] in SUPERVISOR_KINDS and user["id"] == row["supervisor_id"] and has_roles(user, "manager")
        ):
            continue
        visible.append(row)
    history = defaultdict(list)
    if visible:
        for record in repo.history([row["id"] for row in visible]):
            history[record["request_id"]].append(record)
    return [view_request(repo, row, row["employee_name"], history[row["id"]]) for row in visible]


def approve_side_effect(repo, row):
    request_id = row["id"]
    employee_id = row["employee_id"]
    data = row["details"]
    if row["original_id"]:
        source = repo.request(row["original_id"], lock=True)
        if not source or source["status"] != "approved":
            fail(409, "原申請目前無法撤銷。")
        repo.set_status(source["id"], "cancelled")
        return source["id"]
    if row["kind"] == "clock_correction":
        day = date.fromisoformat(data["date"])
        stamp = aware(data["corrected_at"])
        existing = {p["direction"]: p["recorded_at"] for p in repo.clock_events(employee_id, day, day)}
        if (data["direction"] == "in" and "out" in existing and stamp > existing["out"]
                or data["direction"] == "out" and "in" in existing and stamp < existing["in"]):
            fail(409, "補正時間會讓下班早於上班，請退回更正。")
        repo.insert_clock(employee_id, day, data["direction"], stamp, request_id)
    elif row["kind"] == "profile_change":
        # Field names come only from this fixed allowlist.
        for field in ("phone", "address", "emergency_contact"):
            if field in data:
                repo.execute(f"UPDATE employees SET {field}=%s WHERE id=%s", (data[field], employee_id))
    return None


def request_action(repo, user, request_id, action, payload):
    row = repo.request(request_id)
    if row is None:
        fail(404, "找不到這筆申請。")
    employee = repo.lock_employee(row["employee_id"])
    row = repo.request(request_id, lock=True)
    own = user["id"] == row["employee_id"]
    pending = row["status"] == "pending"
    kind = row["kind"]
    reason = payload.reason.strip()
    if len(reason) > 2000:
        fail(422, "原因欄位最多可輸入 2,000 字。")

    if action in {"approve", "return"}:
        row = refresh_assignment(repo, row, employee)
        if not can_review(user, row):
            fail(403, "你沒有審核這筆申請的權限。")
        if not pending:
            fail(409, "這筆申請已處理。")
        if action == "return" and not reason:
            fail(422, "退回申請須填寫原因。")
        if action == "approve":
            source_id = approve_side_effect(repo, row)
            if source_id:
                repo.add_history(source_id, user["id"], "cancelled", "撤銷申請已核准。")
        updated = repo.set_status(request_id, "approved" if action == "approve" else "returned")
        notify(repo.conn, row["employee_id"], f"你的{KIND_LABELS[kind]}申請已{'核准' if action == 'approve' else '退回'}。")
    elif action == "assign":
        require_roles(user, "owner")
        if not pending:
            fail(409, "只能指派待審申請。")
        assignee = repo.employee(payload.reviewer_id) if payload.reviewer_id is not None else None
        needed = ("manager", "owner") if kind in SUPERVISOR_KINDS else ("admin",)
        if (not assignee or not assignee["active"] or assignee["id"] == row["employee_id"]
                or not has_roles(assignee, *needed)):
            fail(422, "請選擇有對應權限且仍在職的審核人。")
        updated = repo.set_reviewer(request_id, assignee["id"], manually=True)
        notify_reviewers(repo, updated)
    elif action == "paid":
        require_roles(user, "admin")
        if kind != "expense" or row["status"] != "approved" or not can_review(user, row):
            fail(409, "只能將其他員工已核准的報帳標記為已付款。")
        updated = repo.set_status(request_id, "paid")
        notify(repo.conn, row["employee_id"], "你的報帳已標記為付款。")
    elif action in {"withdraw", "cancel", "resubmit"}:
        if not own:
            fail(403, "只能修改自己的申請。")
        if not employee["active"]:
            fail(403, "帳號已停用。")
        if action == "withdraw":
            if not pending or kind not in SUPERVISOR_KINDS:
                fail(409, "只能撤回待審的請假、外出、加班或其撤銷單。")
            updated = repo.set_status(request_id, "withdrawn")
        elif action == "cancel":
            if kind not in SUPERVISOR_KINDS or row["status"] != "approved" or row["original_id"]:
                fail(409, "只能送出已核准請假、外出或加班的撤銷申請。")
            if repo.one("SELECT id FROM wf_requests WHERE original_id=%s AND status='pending'", (request_id,)):
                fail(409, "這筆申請已有待審撤銷單。")
            updated = repo.insert_request(user["id"], kind, route_supervisor(repo, employee), row["details"], request_id)
            notify_reviewers(repo, updated)
        else:
            if row["status"] != "returned":
                fail(409, "只能重送已退回的申請。")
            reviewer = route_supervisor(repo, employee) if kind in SUPERVISOR_KINDS else None
            receipt = None
            if row["original_id"]:
                original = repo.request(row["original_id"])
                if original["status"] != "approved" or repo.one(
                    "SELECT id FROM wf_requests WHERE original_id=%s AND id<>%s AND status='pending'",
                    (original["id"], request_id),
                ):
                    fail(409, "原申請目前無法撤銷。")
                details = original["details"]
            else:
                combined = {**row["details"], **(payload.details or {})}
                details, receipt = normalize_request(repo, employee, kind, combined)
                confirm_leave_balance(repo, user["id"], kind, details, request_id)
                if kind == "expense" and not receipt and row["details"].get("attachment_name"):
                    details["attachment_name"] = row["details"]["attachment_name"]
            updated = repo.resubmit(request_id, reviewer, details)
            if receipt:
                repo.put_receipt(updated["id"], *receipt)
            notify_reviewers(repo, updated)
    else:
        fail(404, "找不到此申請操作。")

    repo.add_history(updated["id"], user["id"], action, reason)
    return view_request(repo, updated, employee["name"])


def balance_list(repo, user, employee_id=None):
    owner_id = employee_id or user["id"]
    if owner_id != user["id"]:
        require_roles(user, "owner", "admin")
    results = []
    for item in repo.leave_types():
        configured = repo.balance(owner_id, item["id"])
        totals = repo.leave_used(owner_id, item["id"])
        total = configured["total_minutes"] if configured else (0 if item["requires_balance"] else None)
        remaining = total - totals["used"] - totals["reserved"] if total is not None else None
        results.append({
            **item, "employee_id": owner_id, "leave_type_id": item["id"], "total_minutes": total,
            "used_minutes": totals["used"], "reserved_minutes": totals["reserved"], "remaining_minutes": remaining,
        })
    return results


def set_balance(repo, user, value):
    require_roles(user, "owner", "admin")
    if not repo.lock_employee(value.employee_id) or not repo.leave_type(value.leave_type_id):
        fail(404, "找不到員工或假別。")
    usage = repo.leave_used(value.employee_id, value.leave_type_id)
    if value.total_minutes < usage["used"] + usage["reserved"]:
        fail(409, "總額不得少於已使用或已保留時數。")
    repo.execute(
        """INSERT INTO wf_leave_balances(employee_id,leave_type_id,total_minutes) VALUES (%s,%s,%s)
           ON CONFLICT(employee_id,leave_type_id) DO UPDATE SET total_minutes=excluded.total_minutes""",
        (value.employee_id, value.leave_type_id, value.total_minutes),
    )
    return next(item for item in balance_list(repo, user, value.employee_id) if item["leave_type_id"] == value.leave_type_id)


def add_delegate(repo, user, value):
    require_roles(user, "owner")
    if value.start > value.end or value.supervisor_id == value.reviewer_id:
        fail(422, "請檢查代理對象及期間。")
    repo.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"office-delegate:{value.supervisor_id}",))
    delegate = repo.employee(value.reviewer_id)
    supervisor = repo.employee(value.supervisor_id) if value.supervisor_id is not None else None
    if (not delegate or not delegate["active"] or not has_roles(delegate, "manager", "owner")
            or value.supervisor_id is not None and (not supervisor or not has_roles(supervisor, "manager", "owner"))):
        fail(422, "代理審核人與其代理的主管必須具有主管權限。")
    overlap = repo.one(
        """SELECT id FROM wf_delegates WHERE supervisor_id IS NOT DISTINCT FROM %s
           AND start<=%s AND "end">=%s LIMIT 1""",
        (value.supervisor_id, value.end, value.start),
    )
    if overlap:
        fail(409, "相同主管已有一筆涵蓋此期間的代理設定。")
    saved = repo.one(
        'INSERT INTO wf_delegates(supervisor_id,reviewer_id,start,"end") VALUES (%s,%s,%s,%s) RETURNING *',
        (value.supervisor_id, value.reviewer_id, value.start, value.end),
    )
    if value.start <= today() <= value.end:
        targets = repo.all(
            """SELECT id FROM employees WHERE active AND supervisor_id IS NOT DISTINCT FROM %s
               ORDER BY id""", (value.supervisor_id,),
        )
        for employee in targets:
            actor = repo.lock_employee(employee["id"])
            rows = repo.all(
                "SELECT * FROM wf_requests WHERE employee_id=%s AND status='pending' ORDER BY id FOR UPDATE",
                (employee["id"],),
            )
            for row in rows:
                refresh_assignment(repo, row, actor)
    return saved
