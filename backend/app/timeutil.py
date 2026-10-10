from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Callers use `timeutil.utc_now()` (not a from-import) so tests can replace the clock.


def utc_now() -> datetime:
    """Naive UTC, matching every DateTime column."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime, tz: str) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))


def local_date(dt: datetime, tz: str) -> date:
    return to_local(dt, tz).date()


def local_to_utc(d: date, t: time, tz: str) -> datetime:
    """A wall-clock time in `tz` as naive UTC; DST gaps resolve forward, overlaps to the first occurrence."""
    aware = datetime.combine(d, t, tzinfo=ZoneInfo(tz))
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def shift_end_utc(d: date, start: time, end: time, tz: str) -> datetime:
    """End of a shift starting on local date `d`; an end at or before the start falls on the next day."""
    end_date = d + timedelta(days=1) if end <= start else d
    return local_to_utc(end_date, end, tz)


def shift_minutes(start: time, end: time) -> int:
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    return (e - s) % (24 * 60) or 24 * 60


def aware_to_utc(dt: datetime) -> datetime:
    """Request datetimes must carry an offset; stored as naive UTC."""
    if dt.tzinfo is None:
        raise ValueError("datetime must include a timezone offset")
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
