from datetime import datetime, time

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import ChecklistInstance, ChecklistTask, ChecklistTemplate, Location, Shift

OPEN = ("not_started", "in_progress")
DONE = ("completed", "pending_verification", "verified", "waived")


def effective_status(inst: ChecklistInstance, now: datetime) -> str:
    if inst.status in OPEN and inst.due_at and inst.due_at < now:
        return "overdue"
    return inst.status


def _due_at(task: ChecklistTask, shift: Shift | None, day, tz: str) -> datetime:
    if task.deadline_time:
        return timeutil.local_to_utc(day, task.deadline_time, tz)
    if shift:
        return timeutil.shift_end_utc(day, shift.start_time, shift.end_time, tz)
    return timeutil.local_to_utc(day, time(23, 59), tz)


def generate_for_location(db: Session, location: Location, now: datetime) -> int:
    """Creates today's instances (location-local date); safe to run repeatedly."""
    tz = location.timezone
    today = timeutil.local_date(now, tz)
    weekday = str(today.weekday())
    shifts = {s.id: s for s in db.scalars(select(Shift).where(Shift.active.is_(True)))}
    rows = db.execute(
        select(ChecklistTask, ChecklistTemplate)
        .join(ChecklistTemplate, ChecklistTask.template_id == ChecklistTemplate.id)
        .where(ChecklistTemplate.location_id == location.id, ChecklistTemplate.active.is_(True),
               ChecklistTask.active.is_(True))
    ).all()
    created = 0
    for task, template in rows:
        if (task.active_from and today < task.active_from) or (task.active_to and today > task.active_to):
            continue
        if weekday not in task.weekdays.split(","):
            continue
        targets = [task.shift_id or 0]
        if template.frequency == "per_shift" and not task.shift_id:
            targets = list(shifts)
        for shift_key in targets:
            exists = db.scalar(select(ChecklistInstance.id).where(
                ChecklistInstance.task_id == task.id, ChecklistInstance.local_date == today,
                ChecklistInstance.shift_key == shift_key))
            if exists:
                continue
            try:
                with db.begin_nested():
                    db.add(ChecklistInstance(
                        task_id=task.id, location_id=location.id, local_date=today, shift_key=shift_key,
                        due_at=_due_at(task, shifts.get(shift_key), today, tz),
                        assigned_employee_id=task.assigned_employee_id))
                created += 1
            except IntegrityError:
                continue
    return created


def mark_overdue(db: Session, now: datetime) -> int:
    result = db.execute(update(ChecklistInstance)
                        .where(ChecklistInstance.status.in_(OPEN), ChecklistInstance.due_at < now)
                        .values(status="overdue"))
    return result.rowcount
