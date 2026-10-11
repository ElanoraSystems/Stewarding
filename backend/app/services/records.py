"""Printable record documents: one titled table per location and monitoring point or checklist, for audits and month end."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (ChecklistInstance, ChecklistTask, ChecklistTemplate, CorrectiveAction, Employee, Equipment, Location,
                      TemperatureReading)
from .monitoring import describe

KINDS = {"monitoring": "Monitoring Record", "checklists": "Checklist Record"}
MAX_DAYS = 366


def _local(dt: datetime | None, tz: str) -> str:
    return timeutil.to_local(dt, tz).strftime("%d %b %Y %H:%M") if dt else ""


def _limits(reading: TemperatureReading) -> str:
    if reading.value_type == "yes_no":
        return "Must be Yes"
    low = "-" if reading.min_limit is None else f"{reading.min_limit.normalize():f}"
    high = "-" if reading.max_limit is None else f"{reading.max_limit.normalize():f}"
    return f"{low} to {high} {reading.unit or ''}".strip()


def _bounds(day_from: date, day_to: date, tz: str) -> tuple[datetime, datetime]:
    return (timeutil.local_to_utc(day_from, time(0, 0), tz), timeutil.local_to_utc(day_to + timedelta(days=1), time(0, 0), tz))


def _names(db: Session) -> dict[int, str]:
    return {e.user_id: e.full_name for e in db.scalars(select(Employee)) if e.user_id}


def _locations(db: Session, scope: set[int] | None, location_id: int | None) -> list[Location]:
    stmt = select(Location).where(Location.active.is_(True))
    if location_id is not None:
        stmt = stmt.where(Location.id == location_id)
    elif scope is not None:
        stmt = stmt.where(Location.id.in_(scope))
    return list(db.scalars(stmt.order_by(Location.name)))


def _monitoring_groups(db: Session, locations: list[Location], day_from: date, day_to: date, equipment_id: int | None) -> list[dict]:
    names = _names(db)
    groups = []
    for loc in locations:
        start, end = _bounds(day_from, day_to, loc.timezone)
        stmt = select(Equipment).where(Equipment.location_id == loc.id)
        if equipment_id is not None:
            stmt = stmt.where(Equipment.id == equipment_id)
        for eq in db.scalars(stmt.order_by(Equipment.code)):
            readings = list(db.scalars(select(TemperatureReading).where(
                TemperatureReading.equipment_id == eq.id, TemperatureReading.recorded_at >= start,
                TemperatureReading.recorded_at < end).order_by(TemperatureReading.recorded_at)))
            if not readings:
                continue
            actions = {a.reading_id: a for a in db.scalars(select(CorrectiveAction).where(
                CorrectiveAction.reading_id.in_([r.id for r in readings])))}
            rows = []
            for r in readings:
                a = actions.get(r.id)
                taken = f"{a.action} ({names.get(a.taken_by, '')}, {a.status.replace('_', ' ')})" if a and a.action else (
                    a.status.replace("_", " ") if a else "")
                when = _local(r.recorded_at, loc.timezone)
                rows.append({
                    "date": when[:11], "time": when[12:], "check": r.stage[:1].upper() + r.stage[1:].replace("_", " "), "measure": r.parameter,
                    "value": describe(r.value, r.value_type, r.unit), "limits": _limits(r),
                    "result": "Pass" if r.passed else "FAIL", "reference": r.reference or "",
                    "recorded_by": names.get(r.recorded_by, ""),
                    "approved_by": f"{names.get(r.reviewed_by, '')} {_local(r.reviewed_at, loc.timezone)}".strip() if r.reviewed_at else "Awaiting approval",
                    "corrective_action": taken})
            failed = sum(1 for r in readings if not r.passed)
            groups.append({
                "title": f"{loc.name} - {eq.name} ({eq.code})",
                "meta": [("Location", loc.name), ("Monitoring point", f"{eq.name} ({eq.code})"), ("Type", eq.kind)],
                "columns": [("date", "Date"), ("time", "Time"), ("check", "Check"), ("measure", "Measure"), ("value", "Value"),
                            ("limits", "Limits"), ("result", "Result"), ("reference", "Batch / lot"), ("recorded_by", "Recorded by"),
                            ("approved_by", "Approved by"), ("corrective_action", "Corrective action")],
                "rows": rows,
                "totals": [("Checks recorded", len(readings)), ("Passed", len(readings) - failed), ("Failed", failed),
                           ("Awaiting approval", sum(1 for r in readings if not r.reviewed_at))]})
    return groups


def _checklist_groups(db: Session, locations: list[Location], day_from: date, day_to: date) -> list[dict]:
    names = _names(db)
    groups = []
    for loc in locations:
        rows_by_template: dict[str, list] = {}
        stmt = (select(ChecklistInstance, ChecklistTask, ChecklistTemplate)
                .join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
                .join(ChecklistTemplate, ChecklistTemplate.id == ChecklistTask.template_id)
                .where(ChecklistInstance.location_id == loc.id, ChecklistInstance.local_date >= day_from,
                       ChecklistInstance.local_date <= day_to)
                .order_by(ChecklistInstance.local_date, ChecklistTemplate.name, ChecklistTask.id))
        for inst, task, template in db.execute(stmt):
            rows_by_template.setdefault(f"{template.name} ({template.frequency})", []).append({
                "date": inst.local_date.strftime("%d %b %Y"), "task": task.description, "status": inst.status.replace("_", " "),
                "completed_by": names.get(inst.completed_by, ""), "completed_at": _local(inst.completed_at, loc.timezone),
                "reading": "" if inst.reading is None else f"{inst.reading.normalize():f}",
                "comment": inst.comment or inst.waive_reason or "",
                "verified_by": names.get(inst.verified_by, ""), "verified_at": _local(inst.verified_at, loc.timezone)})
        for title, rows in rows_by_template.items():
            counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("verified", "pending verification", "completed", "failed")}
            groups.append({
                "title": f"{loc.name} - {title}",
                "meta": [("Location", loc.name), ("Checklist", title)],
                "columns": [("date", "Date"), ("task", "Task"), ("status", "Status"), ("completed_by", "Completed by"),
                            ("completed_at", "Completed at"), ("reading", "Reading"), ("comment", "Comment"),
                            ("verified_by", "Approved by"), ("verified_at", "Approved at")],
                "rows": rows,
                "totals": [("Tasks", len(rows)), ("Approved", counts["verified"]), ("Awaiting approval", counts["pending verification"]),
                           ("Rejected", counts["failed"])]})
    return groups


def build_record(db: Session, now: datetime, scope: set[int] | None, kind: str, day_from: date, day_to: date,
                 location_id: int | None, equipment_id: int | None, prepared_by: str) -> dict:
    if kind not in KINDS:
        raise ValueError("Unknown record type")
    if day_from > day_to:
        raise ValueError("The start date is after the end date")
    if (day_to - day_from).days >= MAX_DAYS:
        raise ValueError(f"A record covers at most {MAX_DAYS} days")
    locations = _locations(db, scope, location_id)
    groups = (_monitoring_groups(db, locations, day_from, day_to, equipment_id) if kind == "monitoring"
              else _checklist_groups(db, locations, day_from, day_to))
    label = day_from.strftime("%d %b %Y") if day_from == day_to else f"{day_from.strftime('%d %b %Y')} to {day_to.strftime('%d %b %Y')}"
    return {"kind": kind, "title": KINDS[kind], "period": {"from": day_from.isoformat(), "to": day_to.isoformat(), "label": label},
            "locations": [loc.name for loc in locations], "prepared_by": prepared_by,
            "generated_at": now.strftime("%d %b %Y %H:%M UTC"), "groups": groups}
