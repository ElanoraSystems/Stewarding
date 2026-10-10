from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import (AttendanceRecord, BreakageIncident, ChecklistInstance, ChecklistTask, CorrectiveAction, Equipment,
                      InventoryTransfer, Location, TemperatureReading, User)
from ..permissions import STEWARD
from ..services import metrics
from ..services.checklists import OPEN, effective_status
from ..services.settings import get_setting
from ..services.summary import grouped, pending_items
from ..services.temperature import due_checks, failure_count

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _range(date_from: date | None, date_to: date | None, today: date) -> tuple[date, date]:
    end = date_to or today
    return date_from or end - timedelta(days=13), end


def _percent_block(stats: dict) -> dict:
    return {"numerator": stats["numerator"], "denominator": stats["denominator"], "percent": stats["percent"]}


def _sum_compliance(stats_list: list[dict]) -> dict:
    counts: Counter = Counter()
    for s in stats_list:
        counts.update(s["counts"])
    return {**metrics.compliance(counts), "counts": dict(counts)}


def _equipment_attention(db: Session, scope: set[int] | None, location_id: int | None, now: datetime) -> int:
    stmt = select(Equipment).where(Equipment.active.is_(True))
    if location_id is not None:
        stmt = stmt.where(Equipment.location_id == location_id)
    elif scope is not None:
        stmt = stmt.where(Equipment.location_id.in_(scope))
    limit = get_setting(db, "temp.repeat_failure_count")
    return sum(1 for eq in db.scalars(stmt) if eq.status != "operational" or failure_count(db, eq.id, now) >= limit)


def _manager_view(db: Session, user: User, now: datetime, location_id: int | None, date_from, date_to,
                  employee_id: int | None, equipment_id: int | None, task_status: str | None) -> dict:
    scope = scoped_locations(user, db)
    today_wins = metrics.windows_by(db, now, scope, location_id, lambda t: (t, t))
    week_wins = metrics.windows_by(db, now, scope, location_id, metrics.week_of)
    first = today_wins[0].today if today_wins else timeutil.local_date(now, "UTC")
    d_from, d_to = _range(date_from, date_to, first)
    range_wins = metrics.windows(db, now, scope, location_id, d_from, d_to)

    attendance = [metrics.attendance_stats(db, w, now) for w in today_wins]
    scheduled = sum(a["scheduled"] for a in attendance)
    present = sum(a["present"] for a in attendance)
    on_duty_stmt = select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.open_flag == 1)
    if location_id is not None:
        on_duty_stmt = on_duty_stmt.where(AttendanceRecord.location_id == location_id)
    elif scope is not None:
        on_duty_stmt = on_duty_stmt.where(AttendanceRecord.location_id.in_(scope))
    daily = _sum_compliance([metrics.checklist_stats(db, w, now, not_frequency="weekly") for w in today_wins])
    weekly = _sum_compliance([metrics.checklist_stats(db, w, now, frequency="weekly") for w in week_wins])
    overdue_stmt = select(func.count()).select_from(ChecklistInstance).where(
        ChecklistInstance.status.in_(OPEN + ("overdue",)), ChecklistInstance.due_at < now)
    if location_id is not None:
        overdue_stmt = overdue_stmt.where(ChecklistInstance.location_id == location_id)
    elif scope is not None:
        overdue_stmt = overdue_stmt.where(ChecklistInstance.location_id.in_(scope))
    temp_today = [metrics.temperature_stats(db, w, now) for w in today_wins]
    stock = metrics.stock_snapshot(db, scope, location_id)
    month_wins = metrics.windows_by(db, now, scope, location_id, lambda t: (t.replace(day=1), t))
    kpis = {
        "scheduled_today": scheduled, "checked_in": present, "not_checked_in": scheduled - present,
        "off_today": sum(a["week_off"] + a["on_leave"] for a in attendance),
        "absent": sum(a["absent"] for a in attendance), "on_duty": db.scalar(on_duty_stmt),
        "daily_completion": _percent_block(daily), "weekly_completion": _percent_block(weekly),
        "overdue_tasks": db.scalar(overdue_stmt),
        "temperature_checks": {"done": sum(t["done"] for t in temp_today), "due": sum(t["due"] for t in temp_today)},
        "failed_temperature_checks": sum(t["failed"] for t in temp_today),
        "equipment_attention": _equipment_attention(db, scope, location_id, now),
        "inventory": stock["total"],
        "low_stock_items": len(stock["low"]),
        "breakage_today": len(metrics.breakage_in(db, today_wins)), "breakage_month": len(metrics.breakage_in(db, month_wins)),
    }

    trend: dict[date, Counter] = defaultdict(Counter)
    att_trend: dict[date, dict] = defaultdict(lambda: {k: 0 for k in metrics.ATTENDANCE_KEYS})
    for w in range_wins:
        for day, counts in metrics.checklist_stats(db, w, now, employee_id=employee_id)["per_day"].items():
            trend[day].update(counts)
        for day, vals in metrics.attendance_stats(db, w, now, employee_id)["per_day"].items():
            for key, v in vals.items():
                att_trend[day][key] += v
    task_trend = []
    for day in metrics.daterange(d_from, d_to):
        c = trend.get(day, Counter())
        comp = metrics.compliance(c)
        entry = {"date": day.isoformat(), "done": comp["numerator"], "due": comp["denominator"], "percent": comp["percent"],
                 "overdue": c["overdue"], "failed": c["failed"]}
        if task_status:
            entry["selected"] = c[task_status]
        task_trend.append(entry)

    temp_range = [metrics.temperature_stats(db, w, now, equipment_id) for w in range_wins]
    movement: dict[date, dict] = defaultdict(lambda: {"in": 0, "out": 0})
    for txn, day in metrics.movements(db, range_wins):
        if txn.txn_type in ("receipt", "return"):
            movement[day]["in"] += txn.qty_delta
        elif txn.txn_type in ("issue", "breakage", "damage"):
            movement[day]["out"] += -txn.qty_delta

    months = _breakage_by_month(db, scope, location_id, now)
    return {
        "role": user.role.name, "kpis": kpis,
        "charts": {
            "task_trend": task_trend,
            "weekly_compliance": [{"location": w.loc.name, **_percent_block(metrics.checklist_stats(db, w, now, frequency="weekly"))}
                                  for w in week_wins],
            "temperature_compliance": [{k: e[k] for k in ("equipment", "location", "due", "done", "failed")}
                                       | {"percent": metrics.pct(e["done"], e["due"])}
                                       for t in temp_range for e in t["equipment"].values()],
            "breakage_trend": months,
            "inventory_movement": [{"date": d.isoformat(), **movement.get(d, {"in": 0, "out": 0})}
                                   for d in metrics.daterange(d_from, d_to)],
            "attendance_trend": [{"date": d.isoformat(), **att_trend.get(d, {k: 0 for k in metrics.ATTENDANCE_KEYS})}
                                 for d in metrics.daterange(d_from, d_to) if d <= first],
        },
        "filters": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(), "location_id": location_id},
    }


def _breakage_by_month(db: Session, scope: set[int] | None, location_id: int | None, now: datetime) -> list[dict]:
    tzs = {loc.id: loc.timezone for loc in db.scalars(select(Location))}
    stmt = select(BreakageIncident).where(BreakageIncident.status != "rejected",
                                          BreakageIncident.occurred_at >= now - timedelta(days=190))
    if location_id is not None:
        stmt = stmt.where(BreakageIncident.location_id == location_id)
    elif scope is not None:
        stmt = stmt.where(BreakageIncident.location_id.in_(scope))
    buckets: dict[str, dict] = {}
    cursor = now.replace(day=1)
    for _ in range(6):
        buckets[cursor.strftime("%Y-%m")] = {"incidents": 0, "qty": 0, "est_cost": 0.0}
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    for inc in db.scalars(stmt):
        key = timeutil.to_local(inc.occurred_at, tzs[inc.location_id]).strftime("%Y-%m")
        if key in buckets:
            buckets[key]["incidents"] += 1
            buckets[key]["qty"] += inc.qty
            buckets[key]["est_cost"] += float(inc.est_cost or 0)
    return [{"month": k, **v} for k, v in sorted(buckets.items())]


def _supervisor_extras(db: Session, user: User, now: datetime, location_id: int | None) -> dict:
    scope = scoped_locations(user, db)
    ids = {location_id} if location_id is not None else scope
    items = pending_items(db, ids, now)
    transfers = select(func.count()).select_from(InventoryTransfer).where(InventoryTransfer.status == "requested")
    if ids is not None:
        transfers = transfers.where(InventoryTransfer.from_location_id.in_(ids))
    today_wins = metrics.windows_by(db, now, scope, location_id, lambda t: (t, t))
    staff = [r for w in today_wins for r in metrics.attendance_stats(db, w, now)["rows"]]
    return {
        "pending": {**grouped(items), "items": items[:25]},
        "staff_today": [{"name": r["name"], "shift": r["shift"], "status": r["status"], "late_minutes": r["late_minutes"]} for r in staff],
        "stock_requests": db.scalar(transfers),
        "to_verify": sum(1 for i in items if i["category"] == "verification"),
        "failed_readings_open": sum(1 for i in items if i["category"] == "corrective_action"),
    }


def _steward_view(db: Session, user: User, now: datetime) -> dict:
    emp = user.employee
    scope = scoped_locations(user, db) or set()
    open_rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == emp.id,
                                                        AttendanceRecord.open_flag == 1)) if emp else None
    tasks: Counter = Counter()
    task_rows = []
    for loc in db.scalars(select(Location).where(Location.id.in_(scope), Location.active.is_(True))):
        day = timeutil.local_date(now, loc.timezone)
        rows = db.execute(select(ChecklistInstance, ChecklistTask).join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
                          .where(ChecklistInstance.location_id == loc.id, ChecklistInstance.local_date == day,
                                 or_(ChecklistInstance.assigned_employee_id == (emp.id if emp else -1),
                                     and_(ChecklistInstance.assigned_employee_id.is_(None),
                                          or_(ChecklistTask.assigned_role.is_(None), ChecklistTask.assigned_role == STEWARD))))
                          .order_by(ChecklistInstance.due_at)).all()
        for inst, task in rows:
            state = effective_status(inst, now)
            tasks[state] += 1
            if state not in ("completed", "verified", "waived", "pending_verification"):
                task_rows.append({"id": inst.id, "description": task.description, "status": state,
                                  "due_at": inst.due_at.isoformat() + "Z" if inst.due_at else None})
    equipment = list(db.scalars(select(Equipment).where(Equipment.location_id.in_(scope), Equipment.active.is_(True))))
    checks = due_checks(db, equipment, now)
    issues = db.scalar(select(func.count()).select_from(CorrectiveAction).join(
        TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id).where(
        TemperatureReading.location_id.in_(scope), CorrectiveAction.status != "resolved"))
    total = sum(tasks.values())
    done = tasks["completed"] + tasks["verified"] + tasks["pending_verification"]
    return {
        "role": STEWARD, "checked_in": open_rec is not None,
        "check_in_at": open_rec.check_in_at.isoformat() + "Z" if open_rec else None,
        "tasks": {"total": total, "done": done, "overdue": tasks["overdue"], "outstanding": task_rows[:20]},
        "temperature_checks": {"due": sum(1 for c in checks if c["status"] == "due"),
                               "overdue": sum(1 for c in checks if c["status"] == "overdue")},
        "unresolved_issues": issues,
    }


@router.get("")
def dashboard(location_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
              employee_id: int | None = None, equipment_id: int | None = None,
              task_status: str | None = None, user: User = Depends(require("dashboard.view")),
              db: Session = Depends(get_db)):
    now = timeutil.utc_now()
    if location_id is not None:
        check_location(user, db, location_id)
    if user.role.name == STEWARD:
        return _steward_view(db, user, now)
    try:
        view = _manager_view(db, user, now, location_id, date_from, date_to, employee_id, equipment_id, task_status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    if user.role.name != "manager":
        view["supervisor"] = _supervisor_extras(db, user, now, location_id)
    return view
