"""Named dates from DGPA dataset 14718, separate from office workdays."""

import csv
from datetime import date
from functools import cache
from pathlib import Path


@cache
def _named_dates(year: int) -> tuple[tuple[date, str], ...]:
    path = Path(__file__).with_name("data") / f"dgpa-{year}.csv"
    if not path.exists():
        return ()
    with path.open(encoding="utf-8-sig", newline="") as source:
        return tuple(
            (date.fromisoformat(row["西元日期"]), title)
            for row in csv.DictReader(source)
            if (title := row["備註"].strip())
        )


def holiday_events(start: date, end: date) -> list[dict]:
    return [
        {
            "id": f"dgpa-{day.isoformat()}",
            "date": day,
            "title": title,
            "category": "holiday",
            "workday_override": None,
        }
        for year in range(start.year, end.year + 1)
        for day, title in _named_dates(year)
        if start <= day <= end
    ]
