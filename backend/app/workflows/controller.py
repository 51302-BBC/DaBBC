from calendar import monthrange
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from psycopg.errors import UniqueViolation

from app.core.service import current_user
from app.database import get_db

from . import reports, service
from .model import (
    BalanceInput, ClockInput, DelegateInput, EventInput, LeaveTypeInput, OvertimeInput, ReportInput, RequestInput,
    ReviewInput, ScheduleInput, today,
)
from .repository import Repository

router = APIRouter(tags=["workflows"])
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def repository(conn=Depends(get_db)):
    return Repository(conn)


def excel_response(content, filename):
    return Response(content, media_type=EXCEL, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })


@router.get("/schedule")
def get_schedule(repo=Depends(repository), user=Depends(current_user)):
    return service.schedule_view(repo)


@router.put("/schedule")
def put_schedule(value: ScheduleInput, repo=Depends(repository), user=Depends(current_user)):
    return service.set_schedule(repo, user, value)


@router.get("/attendance")
def get_attendance(start: date | None = None, end: date | None = None, employee_id: int | None = None,
                   repo=Depends(repository), user=Depends(current_user)):
    if start is None:
        start = today() - timedelta(days=13)
    if end is None:
        end = today()
    start, end = reports.period(start, end)
    target = employee_id or user["id"]
    if target != user["id"]:
        service.require_roles(user, "admin", "owner")
        if not repo.employee(target):
            service.fail(404, "找不到員工。")
    return service.attendance(repo, target, start, end)


@router.post("/attendance/clock")
def clock(value: ClockInput, repo=Depends(repository), user=Depends(current_user)):
    return service.punch(repo, user, value.action)


@router.get("/calendar")
def get_calendar(month: str | None = None, repo=Depends(repository), user=Depends(current_user)):
    try:
        start = date.fromisoformat(f"{month}-01") if month else today().replace(day=1)
        if start.year < 1900 or start.year > 2200:
            raise ValueError
        end = start.replace(day=monthrange(start.year, start.month)[1])
    except ValueError:
        service.fail(422, "請使用 YYYY-MM 指定月份。")
    return service.calendar(repo, start, end)


@router.post("/calendar", status_code=201)
def post_calendar(value: EventInput, repo=Depends(repository), user=Depends(current_user)):
    return service.add_calendar_event(repo, user, value)


@router.delete("/calendar/{event_id}", status_code=204)
def delete_calendar(event_id: int, repo=Depends(repository), user=Depends(current_user)):
    service.require_roles(user, "owner", "admin")
    if not repo.one("DELETE FROM wf_events WHERE id=%s RETURNING id", (event_id,)):
        service.fail(404, "找不到此事件。")
    return Response(status_code=204)


@router.get("/leave-types")
def get_leave_types(repo=Depends(repository), user=Depends(current_user)):
    return repo.leave_types()


@router.post("/leave-types", status_code=201)
def post_leave_type(value: LeaveTypeInput, repo=Depends(repository), user=Depends(current_user)):
    service.require_roles(user, "owner", "admin")
    name = value.name.strip()
    if not name:
        service.fail(422, "請填寫假別名稱。")
    try:
        return repo.one("INSERT INTO wf_leave_types(name,requires_balance) VALUES (%s,%s) RETURNING *",
                        (name, value.requires_balance))
    except UniqueViolation:
        service.fail(409, "此假別名稱已存在。")


@router.get("/leave-balances")
def get_balances(employee_id: int | None = None, repo=Depends(repository), user=Depends(current_user)):
    return service.balance_list(repo, user, employee_id)


@router.put("/leave-balances")
def put_balance(value: BalanceInput, repo=Depends(repository), user=Depends(current_user)):
    return service.set_balance(repo, user, value)


@router.get("/overtime-targets")
def overtime_targets(employee_id: int | None = None, repo=Depends(repository), user=Depends(current_user)):
    target = employee_id or user["id"]
    if target != user["id"]:
        service.require_roles(user, "owner", "admin")
    return repo.one("SELECT employee_id,minutes FROM wf_overtime_targets WHERE employee_id=%s", (target,)) or {
        "employee_id": target, "minutes": None,
    }


@router.put("/overtime-targets")
def put_overtime_target(value: OvertimeInput, repo=Depends(repository), user=Depends(current_user)):
    service.require_roles(user, "owner", "admin")
    if not repo.employee(value.employee_id):
        service.fail(404, "找不到員工。")
    return repo.one(
        """INSERT INTO wf_overtime_targets(employee_id,minutes) VALUES (%s,%s)
           ON CONFLICT(employee_id) DO UPDATE SET minutes=excluded.minutes RETURNING *""",
        (value.employee_id, value.minutes),
    )


@router.get("/delegates")
def list_delegates(repo=Depends(repository), user=Depends(current_user)):
    service.require_roles(user, "owner")
    return repo.all(
        """SELECT d.*,e.name reviewer_name,s.name supervisor_name
           FROM wf_delegates d JOIN employees e ON e.id=d.reviewer_id
           LEFT JOIN employees s ON s.id=d.supervisor_id ORDER BY d.start DESC,d.id DESC"""
    )


@router.post("/delegates", status_code=201)
def post_delegate(value: DelegateInput, repo=Depends(repository), user=Depends(current_user)):
    return service.add_delegate(repo, user, value)


@router.get("/requests")
def list_requests(scope: str = "mine", repo=Depends(repository), user=Depends(current_user)):
    return service.request_list(repo, user, scope)


@router.post("/requests", status_code=201)
def post_request(value: RequestInput, repo=Depends(repository), user=Depends(current_user)):
    return service.submit(repo, user, value)


@router.get("/requests/{request_id}/attachment")
def attachment(request_id: int, repo=Depends(repository), user=Depends(current_user)):
    item = next((row for row in service.request_list(repo, user, "all") if row["id"] == request_id), None)
    receipt = repo.receipt(request_id) if item else None
    if not receipt:
        service.fail(404, "找不到此憑證。")
    return Response(
        receipt["content"], media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(receipt['name'], safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/requests/{request_id}/{action}")
def action_request(request_id: int, action: str, value: ReviewInput | None = None,
                   repo=Depends(repository), user=Depends(current_user)):
    return service.request_action(repo, user, request_id, action, value or ReviewInput())


@router.get("/reports")
def get_report(start: date | None = None, end: date | None = None, employee_id: int | None = None,
               repo=Depends(repository), user=Depends(current_user)):
    return reports.report_view(repo, user, start, end, employee_id)


@router.get("/reports/export")
def export_report_preview(start: date | None = None, end: date | None = None, employee_id: int | None = None,
                          repo=Depends(repository), user=Depends(current_user)):
    report = reports.report_view(repo, user, start, end, employee_id)
    content = reports.export_workbook(reports.workbook_rows(report))
    return excel_response(content, f"work-hours-{report['start']}-{report['end']}.xlsx")


@router.post("/reports/export")
def export_report(value: ReportInput, repo=Depends(repository), user=Depends(current_user)):
    content, filename = reports.export_current(repo, user, value.start, value.end, value.employee_id)
    return excel_response(content, filename)


@router.post("/reports/finalize", status_code=201)
def finalize_report(value: ReportInput, repo=Depends(repository), user=Depends(current_user)):
    return reports.finalize(repo, user, value)


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, repo=Depends(repository), user=Depends(current_user)):
    service.require_roles(user, "owner", "admin")
    item = repo.one("SELECT document,period_start,period_end,version FROM wf_reports WHERE id=%s", (report_id,))
    if not item:
        service.fail(404, "找不到此報表版本。")
    return excel_response(
        item["document"], f"work-hours-{item['period_start']}-{item['period_end']}-v{item['version']}.xlsx"
    )
