from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (AbsenceRecord, AttendanceRecord, ChecklistInstance, ChecklistTask, CorrectiveAction, Employee, Equipment,
                      InventoryBalance, InventoryItem, Location, Shift, ShiftAssignment, TemperatureReading)
from ..permissions import MANAGER, STEWARD, SUPERVISOR
from . import summary
from .checklists import OPEN
from .notify import notify, recipients
from .settings import get_setting
from .monitoring import describe, due_checks

SUMMARY_HOUR = time(8, 0)


def _hm(utc: datetime, tz: str) -> str:
    return timeutil.to_local(utc, tz).strftime("%H:%M")


def missing_checkins(db: Session, location: Location, now: datetime) -> int:
    """Scheduled staff who have not checked in once their shift start plus grace has passed."""
    tz = location.timezone
    day = timeutil.local_date(now, tz)
    rows = db.execute(
        select(ShiftAssignment, Employee, Shift).join(Employee, Employee.id == ShiftAssignment.employee_id)
        .join(Shift, Shift.id == ShiftAssignment.shift_id)
        .where(ShiftAssignment.location_id == location.id, ShiftAssignment.weekday == day.weekday(),
               ShiftAssignment.valid_from <= day, Employee.status == "active", Shift.active.is_(True),
               Shift.kind == "work")).all()
    away = set(db.scalars(select(AbsenceRecord.employee_id).where(
        AbsenceRecord.local_date == day, AbsenceRecord.voided_at.is_(None))))
    created = 0
    for assignment, emp, shift in rows:
        if assignment.valid_to and assignment.valid_to < day:
            continue
        start = timeutil.local_to_utc(day, shift.start_time, tz)
        end = timeutil.shift_end_utc(day, shift.start_time, shift.end_time, tz)
        if not (start + timedelta(minutes=shift.grace_minutes) < now < end):
            continue
        if emp.id in away or db.scalar(select(AttendanceRecord.id).where(AttendanceRecord.employee_id == emp.id,
                                                                         AttendanceRecord.local_date == day)):
            continue
        targets = recipients(db, location.id, SUPERVISOR, MANAGER) + ([emp.user_id] if emp.user_id else [])
        created += notify(db, targets, "no_checkin", f"{emp.full_name} has not checked in ({shift.name} started {_hm(start, tz)})",
                          key=f"nocheckin:{emp.id}:{day}:{shift.id}", priority="high", location_id=location.id,
                          link="/attendance")
    return created


def missed_checkouts(db: Session, now: datetime) -> int:
    limit = timedelta(hours=get_setting(db, "attendance.missed_checkout_hours"))
    created = 0
    for rec in db.scalars(select(AttendanceRecord).where(AttendanceRecord.open_flag == 1)):
        if now - rec.check_in_at <= limit:
            continue
        emp = db.get(Employee, rec.employee_id)
        targets = recipients(db, rec.location_id, SUPERVISOR, MANAGER) + ([emp.user_id] if emp.user_id else [])
        created += notify(db, targets, "missed_checkout", f"{emp.full_name} has not checked out", key=f"missedout:{rec.id}",
                          priority="high", location_id=rec.location_id, link="/attendance")
    return created


def checklist_alerts(db: Session, location: Location, now: datetime) -> int:
    """Reminders before a deadline, an alert when it passes, then escalation to supervisor and manager."""
    lead = timedelta(minutes=get_setting(db, "reminder.lead_minutes"))
    to_supervisor = timedelta(minutes=get_setting(db, "escalation.supervisor_after_minutes"))
    to_manager = timedelta(minutes=get_setting(db, "escalation.manager_after_minutes"))
    tz = location.timezone
    rows = db.execute(
        select(ChecklistInstance, ChecklistTask).join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
        .where(ChecklistInstance.location_id == location.id, ChecklistInstance.status.in_(OPEN + ("overdue",)),
               ChecklistInstance.due_at.is_not(None))).all()
    groups: dict[datetime, list[tuple[ChecklistInstance, ChecklistTask]]] = {}
    for inst, task in rows:
        groups.setdefault(inst.due_at, []).append((inst, task))
    created = 0
    for due, members in groups.items():
        stamp, label = due.strftime("%Y%m%d%H%M"), _hm(due, tz)
        count = len(members)
        crew = recipients(db, location.id, STEWARD, SUPERVISOR)
        if due - lead <= now < due:
            created += notify(db, crew, "task_due_soon", f"{count} task(s) due at {label} - {location.name}",
                              key=f"approach:{location.id}:{stamp}", location_id=location.id, due_at=due, link="/daily-checklists")
        if now >= due:
            late = now - due
            created += notify(db, crew, "task_overdue", f"{count} task(s) overdue since {label} - {location.name}",
                              key=f"overdue:{location.id}:{stamp}", priority="high", location_id=location.id,
                              due_at=due, link="/daily-checklists")
            if late >= to_supervisor:
                created += notify(db, recipients(db, location.id, SUPERVISOR), "task_escalated",
                                  f"Escalation: {count} task(s) still open since {label} - {location.name}",
                                  key=f"esc_sup:{location.id}:{stamp}", priority="high", location_id=location.id,
                                  due_at=due, link="/daily-checklists")
            if late >= to_manager:
                created += notify(db, recipients(db, None, MANAGER), "task_escalated",
                                  f"Escalation to manager: {count} task(s) open since {label} - {location.name}",
                                  key=f"esc_mgr:{location.id}:{stamp}", priority="critical", location_id=location.id,
                                  due_at=due, link="/daily-checklists", requires_ack=True)
        for inst, task in members:
            if now >= due and inst.assigned_employee_id:
                emp = db.get(Employee, inst.assigned_employee_id)
                if emp and emp.user_id:
                    created += notify(db, [emp.user_id], "task_overdue", f"Your task is overdue: {task.description}",
                                      key=f"taskover:{inst.id}", priority="high", location_id=location.id, due_at=due,
                                      link="/daily-checklists")
            if task.escalation_minutes is not None and now >= due + timedelta(minutes=task.escalation_minutes):
                created += notify(db, recipients(db, location.id, SUPERVISOR, MANAGER), "task_escalated",
                                  f"Escalation: {task.description}", key=f"esc_task:{inst.id}", priority="high",
                                  location_id=location.id, due_at=due, link="/daily-checklists")
    return created


def monitoring_alerts(db: Session, location: Location, now: datetime) -> int:
    equipment = list(db.scalars(select(Equipment).where(Equipment.location_id == location.id, Equipment.active.is_(True))))
    created = 0
    checks = due_checks(db, equipment, now)
    # earlier overdue slots of a schedule are already missed; only the latest one is worth an alert
    latest_overdue = {c["schedule_id"]: c for c in checks if c["status"] == "overdue"}
    for check in checks:
        if check["status"] == "overdue" and latest_overdue[check["schedule_id"]] is not check:
            continue
        slot = check["slot_at"][:16].replace("-", "").replace(":", "").replace("T", "")
        title = f"{check['equipment']} - {check['stage']} check"
        if check["status"] == "due":
            created += notify(db, recipients(db, location.id, STEWARD, SUPERVISOR), "monitoring_due", f"Check due: {title}",
                              key=f"checkdue:{check['schedule_id']}:{slot}", location_id=location.id, link="/monitoring")
        elif check["status"] == "overdue":
            created += notify(db, recipients(db, location.id, SUPERVISOR, MANAGER), "monitoring_overdue",
                              f"Check overdue: {title}", key=f"checkover:{check['schedule_id']}:{slot}",
                              priority="high", location_id=location.id, link="/monitoring", requires_ack=True)
    return created


def corrective_alerts(db: Session, now: datetime) -> int:
    escalate_after = timedelta(minutes=get_setting(db, "temp.escalate_after_minutes"))
    created = 0
    rows = db.execute(select(CorrectiveAction, TemperatureReading).join(
        TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id)
        .where(CorrectiveAction.status.in_(("action_required", "retest_due", "retest_failed")))).all()
    for action, reading in rows:
        if action.status == "retest_due" and action.retest_due_at and action.retest_due_at < now:
            created += notify(db, recipients(db, reading.location_id, SUPERVISOR) + [action.taken_by], "retest_due",
                              f"Retest overdue for {reading.stage}: {describe(reading)}", key=f"retest:{action.id}",
                              priority="critical", location_id=reading.location_id, link="/monitoring", requires_ack=True)
        if now - reading.recorded_at >= escalate_after and action.escalated_at is None:
            action.escalated_at = now
            created += notify(db, recipients(db, None, MANAGER), "monitoring_escalated",
                              f"Unresolved failed check ({describe(reading)}, {reading.stage})",
                              key=f"check_esc:{action.id}", priority="critical", location_id=reading.location_id,
                              link="/monitoring", requires_ack=True)
    return created


def low_stock(db: Session, now: datetime) -> int:
    created = 0
    rows = db.execute(select(InventoryBalance, InventoryItem).join(InventoryItem, InventoryItem.id == InventoryBalance.item_id)
                      .where(InventoryItem.active.is_(True), InventoryBalance.qty < InventoryItem.min_level)).all()
    for balance, item in rows:
        created += notify(db, recipients(db, balance.location_id, SUPERVISOR, MANAGER), "low_stock",
                          f"Low stock: {item.name} ({balance.qty} left, minimum {item.min_level})",
                          key=f"low:{item.id}:{balance.location_id}:{now.date().isoformat()}", priority="high",
                          location_id=balance.location_id, link="/inventory")
    return created


def daily_summary(db: Session, location: Location, now: datetime) -> int:
    """One pending-activities digest per location per local day, sent after 08:00 local time."""
    tz = location.timezone
    day = timeutil.local_date(now, tz)
    if now < timeutil.local_to_utc(day, SUMMARY_HOUR, tz):
        return 0
    items = summary.pending_items(db, {location.id}, now)
    if not items:
        return 0
    counts = summary.grouped(items)["by_urgency"]
    return notify(db, recipients(db, location.id, SUPERVISOR, MANAGER), "daily_summary",
                  f"Pending activities - {location.name}: {counts['critical']} critical, {counts['high']} high, {counts['normal']} other",
                  key=f"summary:{location.id}:{day}", location_id=location.id, link="/tasks")


def run_alerts(db: Session, now: datetime) -> dict[str, int]:
    totals = {"checkins": 0, "checklists": 0, "monitoring": 0, "summary": 0}
    for location in db.scalars(select(Location).where(Location.active.is_(True))):
        totals["checkins"] += missing_checkins(db, location, now)
        totals["checklists"] += checklist_alerts(db, location, now)
        totals["monitoring"] += monitoring_alerts(db, location, now)
        totals["summary"] += daily_summary(db, location, now)
    totals["checkouts"] = missed_checkouts(db, now)
    totals["corrective"] = corrective_alerts(db, now)
    totals["low_stock"] = low_stock(db, now)
    return totals
