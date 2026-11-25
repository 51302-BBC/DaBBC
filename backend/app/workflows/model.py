from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

TAIPEI = ZoneInfo("Asia/Taipei")
SUPERVISOR_KINDS = {"leave", "outing", "overtime"}
ADMIN_KINDS = {"clock_correction", "expense", "profile_change"}
KINDS = SUPERVISOR_KINDS | ADMIN_KINDS
KIND_LABELS = {
    "leave": "請假", "outing": "外出", "overtime": "加班",
    "clock_correction": "補打卡", "expense": "報帳", "profile_change": "個人資料修改",
}


class RequestInput(BaseModel):
    kind: str
    details: dict = Field(default_factory=dict)


class ReviewInput(BaseModel):
    reason: str = ""
    reviewer_id: int | None = None
    details: dict | None = None


class ClockInput(BaseModel):
    action: str


class ScheduleInput(BaseModel):
    weekdays: list[int]
    start_time: time
    end_time: time
    break_minutes: int = Field(ge=0, le=720)


class EventInput(BaseModel):
    date: date
    title: str = Field(min_length=1, max_length=180)
    category: str
    workday_override: bool | None = None


class LeaveTypeInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    requires_balance: bool = True


class BalanceInput(BaseModel):
    employee_id: int
    leave_type_id: int
    total_minutes: int = Field(ge=0)


class OvertimeInput(BaseModel):
    employee_id: int
    minutes: int = Field(ge=0)


class DelegateInput(BaseModel):
    supervisor_id: int | None = None
    reviewer_id: int
    start: date
    end: date


class ReportInput(BaseModel):
    start: date
    end: date
    employee_id: int | None = None


def today():
    return datetime.now(TAIPEI).date()


def aware(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=TAIPEI) if parsed.tzinfo is None else parsed.astimezone(TAIPEI)


def dates_between(start, end):
    while start <= end:
        yield start
        start += timedelta(days=1)


def duration(start, end):
    return int((end - start).total_seconds() // 60)
