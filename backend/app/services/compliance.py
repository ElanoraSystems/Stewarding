"""How each outlet is keeping up over a period: tasks and monitoring checks done on time, failed readings, what is open now, and when work slips."""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import ChecklistInstance, ChecklistTask, CorrectiveAction, Equipment, Probe, TemperatureReading
from . import calibration, metrics
from .checklists import OPEN, overdue_after
from .monitoring import CLOSED_ACTIONS
from .settings import get_setting

DONE_ON_TIME = ("completed", "pending_verification", "verified")  # waived work is not expected, so it is left out of every count


def task_timing(db: Session, win: metrics.Win, now: datetime, hidden: set[int]) -> dict:
    """Tasks due in the window and how many were finished by their deadline plus grace; a task with no time or shift is due at the day-end rule (stored in `due_at`).

    A task still open counts only once its deadline and grace have passed; a task done late or failed counts as due but not on time.
    """
    grace = timedelta(minutes=get_setting(db, "checklist.grace_minutes"))
    stmt = (select(ChecklistInstance.status, ChecklistInstance.due_at, ChecklistInstance.completed_at)
            .join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
            .where(ChecklistInstance.location_id == win.loc.id, ChecklistInstance.local_date >= win.d_from,
                   ChecklistInstance.local_date <= win.d_to, ChecklistInstance.status != "waived"))
    if hidden:
        stmt = stmt.where(ChecklistTask.template_id.not_in(hidden))
    due = on_time = 0
    hours = [0] * 24
    for status, due_at, completed_at in db.execute(stmt):
        deadline = due_at + grace if due_at else None
        if status in DONE_ON_TIME:
            ok = deadline is None or completed_at is None or completed_at <= deadline
        elif status == "failed" or (deadline is not None and deadline < now):
            ok = False
        else:
            continue  # not due yet
        due += 1
        on_time += ok
        if not ok and due_at:
            hours[timeutil.to_local(due_at, win.loc.timezone).hour] += 1
    return {"due": due, "on_time": on_time, "percent": metrics.pct(on_time, due), "hours": hours}


def _block(done: int, due: int, missed: int, failed: int) -> dict:
    return {"done": done, "due": due, "missed": missed, "failed": failed, "percent": metrics.pct(done, due)}


def outlet_compliance(db: Session, wins: list[metrics.Win], now: datetime, hidden_templates: set[int], hidden_points: set[int],
                      checklists: bool = True, monitoring: bool = True) -> list[dict]:
    """One row per outlet window. A part the viewer may not open is left out of the row (`None`)."""
    ids = [w.loc.id for w in wins]
    ccp = set(db.scalars(select(Equipment.id).where(Equipment.control_level == "ccp", Equipment.location_id.in_(ids)))) if ids else set()
    overdue: dict[int, int] = {}
    actions: dict[int, int] = {}
    if checklists and ids:
        overdue = dict(db.execute(
            select(ChecklistInstance.location_id, func.count()).join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
            .where(ChecklistInstance.location_id.in_(ids), ChecklistInstance.status.in_(OPEN + ("overdue",)),
                   ChecklistInstance.due_at < overdue_after(db, now), ChecklistTask.template_id.not_in(hidden_templates or {0}))
            .group_by(ChecklistInstance.location_id)).all())
    if monitoring and ids:
        actions = dict(db.execute(
            select(TemperatureReading.location_id, func.count()).select_from(CorrectiveAction)
            .join(TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id)
            .where(TemperatureReading.location_id.in_(ids), CorrectiveAction.status.not_in(CLOSED_ACTIONS),
                   TemperatureReading.equipment_id.not_in(hidden_points or {0}))
            .group_by(TemperatureReading.location_id)).all())
    out = []
    for win in wins:
        row: dict = {"location_id": win.loc.id, "location": win.loc.name, "checklists": None, "monitoring": None, "ccp": None,
                     "failed_readings": None, "open_actions": None, "overdue_now": None, "probes": None,
                     "missed_by_hour": {"monitoring": [0] * 24, "tasks": [0] * 24}}
        if checklists:
            timing = task_timing(db, win, now, hidden_templates)
            row["missed_by_hour"]["tasks"] = timing.pop("hours")
            row["checklists"] = timing
            row["overdue_now"] = overdue.get(win.loc.id, 0)
        if monitoring:
            stats = metrics.monitoring_stats(db, win, now, None, hidden_points)
            points = stats["equipment"].values()
            critical = [e for e in points if e["equipment_id"] in ccp]
            row["monitoring"] = _block(stats["done"], stats["due"], stats["missed"], stats["failed"])
            row["ccp"] = _block(sum(e["done"] for e in critical), sum(e["due"] for e in critical),
                                sum(e["missed"] for e in critical), sum(e["failed"] for e in critical))
            for e in points:
                for hour in e["missed_hours"]:
                    row["missed_by_hour"]["monitoring"][hour] += 1
            row["failed_readings"] = stats["failed"]
            row["open_actions"] = actions.get(win.loc.id, 0)
            states = [calibration.status_of(db, p, now)["status"] for p in db.scalars(
                select(Probe).where(Probe.location_id == win.loc.id, Probe.active.is_(True)))]
            row["probes"] = {"total": len(states), "needs_calibration": sum(s in ("never", "failed", "overdue") for s in states),
                             "due_soon": states.count("due_soon")}
        out.append(row)
    return out
