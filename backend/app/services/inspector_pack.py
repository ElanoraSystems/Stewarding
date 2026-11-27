"""The inspector pack: the records a food-safety inspector asks for, bundled into one printable document.

Every chapter reuses a record from records.py (the same rows as Reports); only the summary, the corrective actions and the training table are built here.
"""
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (ChecklistInstance, CorrectiveAction, Employee, EmployeeLocation, Equipment, Location, Probe, ProbeCalibration,
                      TemperatureReading, TrainingAssignment, TrainingCourse)
from .checklists import OPEN
from .monitoring import LEVEL_NAME, describe
from .records import Filters, _bounds, _local, _locations, _names, build_record

MAX_DAYS = 93  # about a quarter: keeps a pack quick to build and sensible to print
MAX_ROWS = 4000
SUMMARY = "Summary"


def _empty(title: str, note: str) -> dict:
    return {"title": title, "meta": [], "columns": [("note", "")], "rows": [], "totals": [], "empty": note}


def _action_groups(db: Session, locations: list[Location], day_from: date, day_to: date) -> list[dict]:
    """Corrective actions for the readings of the period (the same readings as the monitoring records), open and closed, a table per location."""
    names, groups = _names(db), []
    for loc in locations:
        start, end = _bounds(day_from, day_to, loc.timezone)
        rows = []
        for a, r, eq in db.execute(select(CorrectiveAction, TemperatureReading, Equipment).join(TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id)
                                   .join(Equipment, Equipment.id == TemperatureReading.equipment_id)
                                   .where(TemperatureReading.location_id == loc.id, TemperatureReading.recorded_at >= start, TemperatureReading.recorded_at < end)
                                   .order_by(CorrectiveAction.taken_at, CorrectiveAction.id)):
            rows.append({"when": _local(a.taken_at, loc.timezone), "point": f"{eq.name} ({eq.code})", "reading": f"{r.parameter}: {describe(r)}",
                         "action": a.action or "", "by": names.get(a.taken_by, ""), "status": a.status.replace("_", " ").capitalize(),
                         "closed": _local(a.resolved_at, loc.timezone)})
        if rows:
            groups.append({"title": f"{loc.name} - Corrective actions", "meta": [("Location", loc.name)],
                           "columns": [("when", "Taken at"), ("point", "Monitoring point"), ("reading", "Reading that failed"), ("action", "Action taken"),
                                       ("by", "Taken by"), ("status", "Status"), ("closed", "Closed at")],
                           "rows": rows, "totals": [("Actions", len(rows)), ("Open", sum(1 for r in rows if not r["closed"])),
                                                    ("Closed", sum(1 for r in rows if r["closed"]))]})
    return groups


def _training_groups(db: Session, locations: list[Location], day_from: date, day_to: date) -> list[dict]:
    """Courses finished in the period (with certificate numbers) by the people who work at these locations."""
    if not locations:
        return []
    start, end = _bounds(day_from, day_to, locations[0].timezone)
    people = select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id.in_([loc.id for loc in locations]))
    rows = [{"who": e.full_name, "title": e.job_title, "course": c.title, "done": a.completed_at.strftime("%d %b %Y"),
             "score": "" if a.score is None else f"{a.score}%", "certificate": a.certificate_no or ""}
            for a, e, c in db.execute(select(TrainingAssignment, Employee, TrainingCourse).join(Employee, Employee.id == TrainingAssignment.employee_id)
                                      .join(TrainingCourse, TrainingCourse.id == TrainingAssignment.course_id)
                                      .where(TrainingAssignment.completed_at >= start, TrainingAssignment.completed_at < end, Employee.id.in_(people))
                                      .order_by(TrainingAssignment.completed_at, Employee.full_name))]
    if not rows:
        return []
    return [{"title": "Training completed", "meta": [], "columns": [("who", "Employee"), ("title", "Job title"), ("course", "Course"), ("done", "Completed"),
                                                                  ("score", "Score"), ("certificate", "Certificate no.")],
             "rows": rows, "totals": [("Completions", len(rows))]}]


def _summary(db: Session, locations: list[Location], day_from: date, day_to: date, now: datetime) -> dict:
    ids = [loc.id for loc in locations]
    bounds = [_bounds(day_from, day_to, loc.timezone) for loc in locations] or [(None, None)]
    start, end = min(b[0] for b in bounds if b[0]) if locations else None, max(b[1] for b in bounds if b[1]) if locations else None
    n = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    readings = select(func.count(TemperatureReading.id)).where(TemperatureReading.location_id.in_(ids), TemperatureReading.recorded_at >= start, TemperatureReading.recorded_at < end)
    tasks = select(func.count(ChecklistInstance.id)).where(ChecklistInstance.location_id.in_(ids), ChecklistInstance.local_date >= day_from, ChecklistInstance.local_date <= day_to)
    rows = [("Monitoring readings", n(readings)), ("Readings outside their limit", n(readings.where(TemperatureReading.passed.is_(False)))),
            ("Corrective actions", n(select(func.count(CorrectiveAction.id)).join(TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id)
                                     .where(TemperatureReading.location_id.in_(ids), TemperatureReading.recorded_at >= start, TemperatureReading.recorded_at < end))),
            ("Probe calibration checks", n(select(func.count(ProbeCalibration.id)).join(Probe, Probe.id == ProbeCalibration.probe_id)
                                           .where(Probe.location_id.in_(ids), ProbeCalibration.calibrated_at >= start, ProbeCalibration.calibrated_at < end))),
            ("Checklist tasks done late", n(tasks.where(ChecklistInstance.late_minutes > 0))),
            ("Checklist tasks missed (never done)", n(tasks.where(ChecklistInstance.status.in_(OPEN + ("overdue",)), ChecklistInstance.local_date < now.date())))]
    return {"title": "Summary of the period", "meta": [], "columns": [("measure", "What"), ("count", "How many")],
            "rows": [{"measure": m, "count": c} for m, c in rows], "totals": []}


def _level_rank(group: dict) -> int:
    level = dict(group["meta"]).get("Control level")
    return 0 if level == LEVEL_NAME["ccp"] else 1 if level == LEVEL_NAME["oprp"] else 2


def build_pack(db: Session, now: datetime, scope: set[int] | None, day_from: date, day_to: date, location_id: int | None, prepared_by: str,
               can_see_lots: bool) -> dict:
    """The pack as one record-shaped document: the first group of each chapter carries a 'chapter' heading."""
    if day_from > day_to:
        raise ValueError("The start date is after the end date")
    if (day_to - day_from).days >= MAX_DAYS:
        raise ValueError(f"An inspector pack covers at most {MAX_DAYS} days. Choose a shorter period.")
    f = Filters(location_id=location_id)
    locations = _locations(db, scope, location_id)

    def record(kind: str) -> list[dict]:
        return build_record(db, now, scope, kind, day_from, day_to, f, prepared_by)["groups"]

    chapters = [(SUMMARY, [_summary(db, locations, day_from, day_to, now)], ""),
                ("Monitoring records (critical and operational control points first)", sorted(record("monitoring"), key=_level_rank),  # stable: CCP, OPRP, the rest
                 "No monitoring points recorded in this period."),
                ("Corrective actions taken", _action_groups(db, locations, day_from, day_to), "No corrective actions were taken in this period."),
                ("Probe calibration record", record("calibration"), "No probe calibration checks in this period."),
                ("Checklist record", record("checklists"), "No checklist tasks in this period."),
                ("Approvals and rejections", record("approvals"), "No approvals or rejections in this period.")]
    training = _training_groups(db, locations, day_from, day_to)
    if training:  # no training data: the chapter is left out rather than printed empty
        chapters.append(("Staff training", training, ""))
    if can_see_lots:
        chapters.append(("Lot register", record("lots"), "No lots were received in this period."))
    groups, contents, total = [], [], 0
    for number, (title, found, none) in enumerate(chapters, 1):
        heading = f"{number}. {title}"
        contents.append(heading)
        total += sum(len(g["rows"]) for g in found)
        if title != SUMMARY and not any(g["rows"] for g in found):
            found = [_empty(title, none)]
        groups += [{**found[0], "chapter": heading}, *found[1:]]
    if total > MAX_ROWS:
        raise ValueError(f"This pack has {total:,} rows, more than a PDF can hold ({MAX_ROWS:,}). Choose a shorter period or one location.")
    label = day_from.strftime("%d %b %Y") if day_from == day_to else f"{day_from.strftime('%d %b %Y')} to {day_to.strftime('%d %b %Y')}"
    return {"kind": "inspector_pack", "title": "Inspector pack", "period": {"from": day_from.isoformat(), "to": day_to.isoformat(), "label": label},
            "locations": [loc.name for loc in locations], "prepared_by": prepared_by, "groups": groups, "contents": contents}
