"""Day-count year fractions. Phase 1 runs on whole monthly periods with
30/360, so accrual = rate/12; ACT/360 and ACT/365 calendars land in Phase 2."""

from datetime import date

from ..models.common import DayCount


def year_frac(start: date, end: date, convention: DayCount) -> float:
    if convention == DayCount.THIRTY_360:
        d1 = min(start.day, 30)
        d2 = min(end.day, 30) if d1 == 30 else end.day
        days = (end.year - start.year) * 360 + (end.month - start.month) * 30 + (d2 - d1)
        return days / 360.0
    if convention == DayCount.ACT_360:
        return (end - start).days / 360.0
    if convention == DayCount.ACT_365:
        return (end - start).days / 365.0
    raise ValueError(convention)
