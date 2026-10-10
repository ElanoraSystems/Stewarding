from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (CorrectiveAction, Equipment, EquipmentSchedule, Location, Notification, Shift,
                      TemperatureReading)
from .settings import get_setting

DEFAULT_START = time(6, 0)


def evaluate(value: Decimal, minimum: Decimal | None, maximum: Decimal | None) -> bool:
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def describe(value: Decimal, value_type: str, unit: str | None) -> str:
    """A reading as people say it: 'Yes', 'No' or the number with its unit."""
    if value_type == "yes_no":
        return "Yes" if value == 1 else "No"
    return f"{value.normalize():f} {unit}".strip() if unit else f"{value.normalize():f}"


def applies_on(schedule: EquipmentSchedule, day) -> bool:
    """Whether the check is due on this local date, by weekday list and day of month."""
    if schedule.weekdays and str(day.weekday()) not in schedule.weekdays.split(","):
        return False
    return schedule.day_of_month is None or day.day == schedule.day_of_month


def expected_slots(schedule: EquipmentSchedule, shift: Shift | None, tz: str, day) -> list[datetime]:
    """UTC check times for one schedule on a location-local date; none when the check is not due that day."""
    if not applies_on(schedule, day):
        return []
    start = schedule.time_of_day or (shift.start_time if shift else DEFAULT_START)
    first = timeutil.local_to_utc(day, start, tz)
    if schedule.timing != "interval" or not schedule.interval_minutes:
        return [first]
    end = (timeutil.shift_end_utc(day, shift.start_time, shift.end_time, tz) if shift
           else timeutil.local_to_utc(day + timedelta(days=1), time(0, 0), tz))
    slots, current = [], first
    while current < end:
        slots.append(current)
        current += timedelta(minutes=schedule.interval_minutes)
    return slots


def slot_status(slot: datetime, upper: datetime, readings: list[datetime], now: datetime, grace: int) -> str:
    window_start = slot - timedelta(minutes=grace)
    if any(window_start <= r < upper for r in readings):
        return "done"
    if now < slot:
        return "upcoming"
    return "due" if now <= slot + timedelta(minutes=grace) else "overdue"


def due_checks(db: Session, equipment: list[Equipment], now: datetime) -> list[dict]:
    """Every expected check today for the given equipment, with done/due/overdue/upcoming status."""
    grace = get_setting(db, "temp.due_grace_minutes")
    shifts = {s.id: s for s in db.scalars(select(Shift))}
    locations = {loc.id: loc for loc in db.scalars(select(Location))}
    out = []
    for eq in equipment:
        if not eq.active:
            continue
        tz = locations[eq.location_id].timezone
        day = timeutil.local_date(now, tz)
        day_start = timeutil.local_to_utc(day, time(0, 0), tz) - timedelta(minutes=grace)
        for sched in db.scalars(select(EquipmentSchedule).where(EquipmentSchedule.equipment_id == eq.id,
                                                                EquipmentSchedule.active.is_(True))):
            slots = expected_slots(sched, shifts.get(sched.shift_id), tz, day)
            end_of_day = timeutil.local_to_utc(day + timedelta(days=1), time(0, 0), tz)
            times = list(db.scalars(select(TemperatureReading.recorded_at).where(
                TemperatureReading.schedule_id == sched.id, TemperatureReading.retest_of_id.is_(None),
                TemperatureReading.recorded_at >= day_start)))
            for i, slot in enumerate(slots):
                upper = slots[i + 1] if i + 1 < len(slots) else end_of_day
                out.append({"equipment_id": eq.id, "equipment": eq.name, "location_id": eq.location_id,
                            "schedule_id": sched.id, "stage": sched.stage,
                            "slot_at": slot.isoformat() + "Z", "status": slot_status(slot, upper, times, now, grace)})
    return out


def resolve_alerts(db: Session, reading_id: int, now: datetime) -> None:
    db.execute(update(Notification).where(Notification.dedupe_key == f"temp_fail:{reading_id}",
                                          Notification.resolved_at.is_(None)).values(resolved_at=now))


def resolve_chain(db: Session, reading: TemperatureReading, now: datetime) -> None:
    """A passing retest closes the open corrective action on every earlier reading in its chain."""
    previous_id = reading.retest_of_id
    while previous_id:
        for action in db.scalars(select(CorrectiveAction).where(CorrectiveAction.reading_id == previous_id,
                                                                CorrectiveAction.status != "resolved")):
            action.status, action.resolved_at = "resolved", now
        resolve_alerts(db, previous_id, now)
        previous_id = db.scalar(select(TemperatureReading.retest_of_id).where(TemperatureReading.id == previous_id))


def failure_count(db: Session, equipment_id: int, now: datetime) -> int:
    since = now - timedelta(days=get_setting(db, "temp.repeat_failure_days"))
    return db.scalar(select(func.count()).select_from(TemperatureReading).where(
        TemperatureReading.equipment_id == equipment_id, TemperatureReading.passed.is_(False),
        TemperatureReading.recorded_at >= since))
