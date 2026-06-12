"""US business-day calendar + following-day adjustment.

Used for ACT day-count accrual between adjusted payment dates (e.g. money
market tranches); 30/360 classes conventionally accrue on unadjusted dates.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) given weekday (Mon=0) of a month; n=-1 for the last."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7 + (n - 1) * 7
        return d + timedelta(days=offset)
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    """Fixed-date holiday observance: Sat -> Fri, Sun -> Mon."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def us_federal_holidays(year: int) -> frozenset[date]:
    fixed = [date(year, 1, 1), date(year, 6, 19), date(year, 7, 4),
             date(year, 11, 11), date(year, 12, 25)]
    floating = [
        _nth_weekday(year, 1, 0, 3),   # MLK
        _nth_weekday(year, 2, 0, 3),   # Presidents
        _nth_weekday(year, 5, 0, -1),  # Memorial
        _nth_weekday(year, 9, 0, 1),   # Labor
        _nth_weekday(year, 10, 0, 2),  # Columbus
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
    ]
    return frozenset([_observed(d) for d in fixed] + floating)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in us_federal_holidays(d.year)


def adjust_following(d: date) -> date:
    while not is_business_day(d):
        d += timedelta(days=1)
    return d
