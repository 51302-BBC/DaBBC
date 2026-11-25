import json
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from .model import TAIPEI, aware, duration, today
from .service import attendance, configured_workdays, fail, has_roles, require_roles

REPORT_NOTE = "預覽用工時資料。正式工時與勞動法令適用規則尚待確認。"


def period(start, end):
    first = today().replace(day=1)
    start = start or first
    end = end or (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if start > end or (end - start).days >= 366 or end >= date.max:
        fail(422, "請輸入有效日期範圍，每份報表最多 366 日。")
    return start, end


def file_version_allowed(user):
    role = os.environ.get("REPORT_FINALIZER_ROLE")
    return role in {"admin", "owner"} and has_roles(user, role)


def report_view(repo, user, start, end, employee_id):
    require_roles(user, "owner", "admin")
    start, end = period(start, end)
    people = repo.employees()
    if employee_id is not None:
        people = [person for person in people if person["id"] == employee_id]
        if not people:
            fail(404, "找不到員工。")
    config = configured_workdays(repo, start, end)
    schedule, workdays = config
    approved = defaultdict(dict)
    overtime_windows = defaultdict(list)
    rows = repo.all(
        """SELECT employee_id,kind,details FROM wf_requests WHERE status='approved' AND original_id IS NULL
           AND kind IN ('leave','overtime','outing') AND (details->>'start_at')::timestamptz < %s
           AND (details->>'end_at')::timestamptz > %s""",
        (datetime.combine(end + timedelta(days=1), time.min, TAIPEI), datetime.combine(start, time.min, TAIPEI)),
    )
    for row in rows:
        details = row["details"]
        start_at, end_at = aware(details["start_at"]), aware(details["end_at"])
        # Cross-day approvals are shown from their start day only when an explicit duration
        # differs from the raw interval. The report also flags these for manual allocation.
        for day in workdays:
            begin = max(start_at, datetime.combine(day, time.min, TAIPEI))
            finish = min(end_at, datetime.combine(day + timedelta(days=1), time.min, TAIPEI))
            if begin >= finish:
                continue
            group = approved[row["employee_id"]].setdefault(day, defaultdict(int))
            amount = duration(begin, finish)
            if details["minutes"] != duration(start_at, end_at):
                group["manual_allocation"] += int(start_at.date() != (end_at - timedelta(microseconds=1)).date())
                amount = details["minutes"] if day == start_at.date() else 0
            group[row["kind"]] += amount
            if row["kind"] == "overtime" and amount:
                overtime_windows[row["employee_id"], day].append((begin, finish, amount))
    records, summary = [], []
    for person in people:
        per_person = []
        for row in attendance(repo, person["id"], start, end, config):
            outside_service = (
                person["started_on"] and row["date"] < person["started_on"]
                or person["inactive_on"] and row["date"] > person["inactive_on"]
            )
            if outside_service and not (row["clock_in"] or row["clock_out"]):
                continue
            minutes = approved[person["id"]].get(row["date"], {})
            normal = None
            if schedule and row["expected_workday"] and row["clock_in"] and row["clock_out"]:
                day = row["date"]
                begin = max(row["clock_in"], datetime.combine(day, schedule["start_time"], TAIPEI))
                ending = min(row["clock_out"], datetime.combine(day, schedule["end_time"], TAIPEI))
                normal = max(0, duration(begin, ending) - schedule["break_minutes"])
            flags = []
            if row["status"] in {"missing_punch", "no_record"}:
                flags.append(row["status"])
            for begin, finish, amount in overtime_windows[person["id"], row["date"]]:
                if not row["clock_in"] or not row["clock_out"] or duration(
                    max(row["clock_in"], begin), min(row["clock_out"], finish)
                ) < amount:
                    flags.append("overtime_mismatch")
                    break
            if minutes.get("manual_allocation"):
                flags.append("manual_allocation")
            per_person.append({
                **row, "employee_name": person["name"], "normal_minutes": normal,
                "overtime_minutes": minutes.get("overtime", 0), "leave_minutes": minutes.get("leave", 0),
                "outing_minutes": minutes.get("outing", 0), "flags": flags,
            })
        records.extend(per_person)
        summary.append({
            "employee_id": person["id"], "employee_name": person["name"],
            **{key: sum(record[key] or 0 for record in per_person) for key in (
                "worked_minutes", "normal_minutes", "overtime_minutes", "leave_minutes", "outing_minutes"
            )},
        })
    return {
        "start": start, "end": end, "rows": records, "summary": summary,
        "versions": repo.report_versions(start, end, employee_id),
        "calculation_configured": schedule is not None, "formal_compliance_verified": False,
        "can_finalize": file_version_allowed(user), "note": REPORT_NOTE,
    }


def workbook_rows(report):
    daily = [
        [REPORT_NOTE],
        ["員工", "日期", "上班", "下班", "正常分鐘（預覽）", "加班分鐘", "請假分鐘", "外出分鐘", "狀態", "異常"],
    ]
    for row in report["rows"]:
        daily.append([
            row["employee_name"], row["date"].isoformat(),
            row["clock_in"].strftime("%H:%M") if row["clock_in"] else "",
            row["clock_out"].strftime("%H:%M") if row["clock_out"] else "",
            row["normal_minutes"], row["overtime_minutes"], row["leave_minutes"], row["outing_minutes"],
            row["status"], ", ".join(row["flags"]),
        ])
    totals = [
        [REPORT_NOTE],
        ["員工", "打卡區間分鐘", "正常分鐘（預覽）", "加班分鐘", "請假分鐘", "外出分鐘"],
    ]
    for row in report["summary"]:
        totals.append([row[key] for key in (
            "employee_name", "worked_minutes", "normal_minutes", "overtime_minutes", "leave_minutes", "outing_minutes"
        )])
    return {"逐日工時": daily, "假勤與工時彙總": totals}


def sheets_fingerprint(sheets):
    normalized = {}
    for name, rows in sheets.items():
        values = []
        for row in rows:
            cells = [None if cell == "" else cell for cell in row]
            while cells and cells[-1] is None:
                cells.pop()
            values.append(cells)
        normalized[name] = values
    return sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def stored_fingerprint(content):
    workbook = load_workbook(BytesIO(content), read_only=True)
    try:
        return sheets_fingerprint({sheet.title: sheet.values for sheet in workbook})
    finally:
        workbook.close()


def export_workbook(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    for page in workbook:
        page.freeze_panes = "C3"
        page.auto_filter.ref = f"A2:{page.cell(page.max_row, page.max_column).coordinate}"
        for record in page.iter_rows():
            for cell in record:
                # Employee-supplied strings must be plain text in Excel.
                if cell.data_type == "f":
                    cell.data_type = "s"
                if cell.row == 2:
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="11334D")
                page.column_dimensions[cell.column_letter].width = 20
        page.column_dimensions["A"].width = 28
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def finalize(repo, user, value):
    require_roles(user, "admin", "owner")
    if not file_version_allowed(user):
        fail(409, "月結定稿授權尚未設定。")
    start, end = period(value.start, value.end)
    repo.lock_report_period(start, end, value.employee_id)
    report = report_view(repo, user, start, end, value.employee_id)
    sheets = workbook_rows(report)
    versions = report["versions"]
    return repo.save_report(
        start, end, value.employee_id, user["id"], versions[0]["version"] + 1 if versions else 1,
        sheets_fingerprint(sheets), export_workbook(sheets),
    )


def export_current(repo, user, start, end, employee_id):
    require_roles(user, "admin", "owner")
    start, end = period(start, end)
    allowed = file_version_allowed(user)
    if allowed:
        # Build the snapshot after obtaining the lock so concurrent exports cannot
        # append a revision based on data older than the snapshot ahead of it.
        repo.lock_report_period(start, end, employee_id)
    report = report_view(repo, user, start, end, employee_id)
    sheets = workbook_rows(report)
    filename = f"work-hours-{start}-{end}"
    if not allowed or not report["versions"]:
        return export_workbook(sheets), f"{filename}.xlsx"

    latest = report["versions"][0]
    previous = repo.report_snapshot(latest["id"])
    previous_hash = previous["content_hash"]
    if previous_hash is None:
        # Existing deployments can have saved reports from before fingerprinting.
        previous_hash = stored_fingerprint(previous["document"])
        repo.set_report_content_hash(latest["id"], previous_hash)
    content_hash = sheets_fingerprint(sheets)
    if content_hash == previous_hash:
        return previous["document"], f"{filename}-v{latest['version']}.xlsx"
    content = export_workbook(sheets)
    version = latest["version"] + 1
    repo.save_report(start, end, employee_id, user["id"], version, content_hash, content)
    return content, f"{filename}-v{version}.xlsx"
