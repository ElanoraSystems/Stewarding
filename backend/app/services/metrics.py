from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (AttendanceRecord, BreakageIncident, ChecklistInstance, ChecklistTask, ChecklistTemplate,
                      CorrectiveAction, Employee, Equipment, EquipmentSchedule, InventoryBalance, InventoryItem,
                      Location, Shift, ShiftAssignment, StockTransaction, TemperatureReading)
from .settings import get_setting
from .temperature import expected_slots

DONE = ("completed", "verified", "pending_verification")
OPEN_STATES = ("not_started", "in_progress", "overdue")
MAX_DAYS = 93


@dataclass
class Win:
    """One location over a local-date range, with the matching UTC bounds."""

    loc: Location
    d_from: date
    d_to: date
    start: datetime
    end: datetime
    today: date


def windows_by(db: Session, now: datetime, scope: set[int] | None, location_id: int | None, span) -> list[Win]:
    """One window per location; `span(local_today)` returns that location's (from, to) local dates."""
    stmt = select(Location).where(Location.active.is_(True)).order_by(Location.name)
    if location_id is not None:
        stmt = stmt.where(Location.id == location_id)
    out = []
    for loc in db.scalars(stmt):
        if scope is not None and loc.id not in scope:
            continue
        tz = loc.timezone
        today = timeutil.local_date(now, tz)
        d_from, d_to = span(today)
        if d_to < d_from:
            raise ValueError("End date is before start date")
        if (d_to - d_from).days >= MAX_DAYS:
            raise ValueError(f"Date range is limited to {MAX_DAYS} days")
        out.append(Win(loc, d_from, d_to, timeutil.local_to_utc(d_from, time(0), tz),
                       timeutil.local_to_utc(d_to + timedelta(days=1), time(0), tz), today))
    return out


def windows(db: Session, now: datetime, scope: set[int] | None, location_id: int | None, d_from: date,
            d_to: date) -> list[Win]:
    return windows_by(db, now, scope, location_id, lambda _today: (d_from, d_to))


def week_of(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def daterange(a: date, b: date):
    for n in range((b - a).days + 1):
        yield a + timedelta(days=n)


def pct(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def classify(inst: ChecklistInstance, now: datetime) -> str:
    if inst.status in DONE or inst.status in ("waived", "failed"):
        return inst.status
    return "overdue" if inst.due_at and inst.due_at < now else "upcoming"


def compliance(counts: Counter) -> dict:
    """Done work over work that is due: future tasks and waived tasks are excluded from the denominator."""
    numerator = sum(counts[s] for s in DONE)
    denominator = numerator + counts["failed"] + counts["overdue"]
    return {"numerator": numerator, "denominator": denominator, "percent": pct(numerator, denominator)}


def checklist_stats(db: Session, win: Win, now: datetime, employee_id: int | None = None,
                    frequency: str | None = None, not_frequency: str | None = None) -> dict:
    stmt = (select(ChecklistInstance, ChecklistTask, ChecklistTemplate)
            .join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
            .join(ChecklistTemplate, ChecklistTemplate.id == ChecklistTask.template_id)
            .where(ChecklistInstance.location_id == win.loc.id, ChecklistInstance.local_date >= win.d_from,
                   ChecklistInstance.local_date <= win.d_to))
    if frequency:
        stmt = stmt.where(ChecklistTemplate.frequency == frequency)
    if not_frequency:
        stmt = stmt.where(ChecklistTemplate.frequency != not_frequency)
    if employee_id is not None:
        emp = db.get(Employee, employee_id)
        stmt = stmt.where((ChecklistInstance.assigned_employee_id == employee_id)
                          | (ChecklistInstance.completed_by == (emp.user_id if emp else -1)))
    rows = db.execute(stmt.order_by(ChecklistInstance.local_date, ChecklistInstance.due_at)).all()
    counts: Counter = Counter()
    per_day: dict[date, Counter] = defaultdict(Counter)
    rows_out = []
    for inst, task, tpl in rows:
        state = classify(inst, now)
        counts[state] += 1
        per_day[inst.local_date][state] += 1
        rows_out.append((inst, task, tpl, state))
    return {"counts": counts, **compliance(counts), "per_day": per_day, "rows": rows_out}


def attendance_stats(db: Session, win: Win, now: datetime, employee_id: int | None = None) -> dict:
    """Expected employee-days from assignments versus actual records; future days are never counted as absent."""
    last = min(win.d_to, win.today)
    tz = win.loc.timezone
    empty = {"rows": [], "per_day": {}, "scheduled": 0, "present": 0, "late": 0, "absent": 0}
    if last < win.d_from:
        return empty
    emp_filter = (Employee.id == employee_id,) if employee_id is not None else ()
    assigns = db.execute(
        select(ShiftAssignment, Employee, Shift).join(Employee, Employee.id == ShiftAssignment.employee_id)
        .join(Shift, Shift.id == ShiftAssignment.shift_id)
        .where(ShiftAssignment.location_id == win.loc.id, Employee.status == "active", *emp_filter)).all()
    records = {}
    for rec in db.scalars(select(AttendanceRecord).where(
            AttendanceRecord.location_id == win.loc.id, AttendanceRecord.local_date >= win.d_from,
            AttendanceRecord.local_date <= last, *( (AttendanceRecord.employee_id == employee_id,) if employee_id is not None else ()))):
        records.setdefault((rec.employee_id, rec.local_date), rec)
    names = {e.id: e.full_name for e in db.scalars(select(Employee))}
    shifts = {s.id: s for s in db.scalars(select(Shift))}
    missed_hours = get_setting(db, "attendance.missed_checkout_hours")
    expected: dict[tuple[int, date], tuple[ShiftAssignment, Shift]] = {}
    for day in daterange(win.d_from, last):
        for a, emp, shift in assigns:
            if a.weekday != day.weekday() or a.valid_from > day or (a.valid_to and a.valid_to < day):
                continue
            current = expected.get((emp.id, day))
            if current is None or shift.start_time < current[1].start_time:
                expected[(emp.id, day)] = (a, shift)
    rows, per_day = [], defaultdict(lambda: {"scheduled": 0, "present": 0, "late": 0, "absent": 0})
    totals = {"scheduled": 0, "present": 0, "late": 0, "absent": 0}

    def row(emp_id, day, shift, rec, status):
        return {"employee_id": emp_id, "name": names.get(emp_id), "day": day, "shift": shift.name if shift else None,
                "status": status, "check_in": rec.check_in_at if rec else None,
                "check_out": rec.check_out_at if rec else None, "late_minutes": rec.late_minutes if rec else 0,
                "payable_minutes": rec.payable_minutes if rec else None,
                "overtime_minutes": rec.overtime_minutes if rec else None}

    for (emp_id, day), (_, shift) in sorted(expected.items(), key=lambda kv: (kv[0][1], names.get(kv[0][0], ""))):
        rec = records.get((emp_id, day))
        per_day[day]["scheduled"] += 1
        totals["scheduled"] += 1
        if rec:
            status = "late" if rec.late_minutes > 0 else "present"
            if rec.open_flag == 1:
                status = "missed_checkout" if (now - rec.check_in_at).total_seconds() > missed_hours * 3600 else "on_duty"
            per_day[day]["present"] += 1
            totals["present"] += 1
            if rec.late_minutes > 0:
                per_day[day]["late"] += 1
                totals["late"] += 1
        else:
            start = timeutil.local_to_utc(day, shift.start_time, tz)
            if day < win.today or now > start + timedelta(minutes=shift.grace_minutes):
                status = "absent"
                per_day[day]["absent"] += 1
                totals["absent"] += 1
            else:
                status = "not_yet_due"
        rows.append(row(emp_id, day, shift, rec, status))
    for (emp_id, day), rec in records.items():
        if (emp_id, day) not in expected:
            rows.append(row(emp_id, day, shifts.get(rec.shift_id), rec, "unscheduled"))
    return {"rows": rows, "per_day": dict(per_day), **totals}


def temperature_stats(db: Session, win: Win, now: datetime, equipment_id: int | None = None) -> dict:
    """Checks due so far versus recorded, per equipment, plus failed readings in the window."""
    grace = timedelta(minutes=get_setting(db, "temp.due_grace_minutes"))
    stmt = select(Equipment).where(Equipment.location_id == win.loc.id, Equipment.active.is_(True))
    if equipment_id is not None:
        stmt = stmt.where(Equipment.id == equipment_id)
    shifts = {s.id: s for s in db.scalars(select(Shift))}
    last = min(win.d_to, win.today)
    out: dict[int, dict] = {}
    for eq in db.scalars(stmt.order_by(Equipment.code)):
        entry = {"equipment_id": eq.id, "equipment": eq.name, "location": win.loc.name, "due": 0, "done": 0, "missed": 0,
                 "failed": 0, "readings": 0}
        readings = db.scalars(select(TemperatureReading).where(
            TemperatureReading.equipment_id == eq.id, TemperatureReading.recorded_at >= win.start - grace,
            TemperatureReading.recorded_at < win.end)).all()
        entry["readings"] = sum(1 for r in readings if win.start <= r.recorded_at < win.end)
        entry["failed"] = sum(1 for r in readings if not r.passed and win.start <= r.recorded_at < win.end)
        if last >= win.d_from:
            for sched in db.scalars(select(EquipmentSchedule).where(EquipmentSchedule.equipment_id == eq.id,
                                                                    EquipmentSchedule.active.is_(True))):
                times = [r.recorded_at for r in readings if r.schedule_id == sched.id and r.retest_of_id is None]
                for day in daterange(win.d_from, last):
                    slots = expected_slots(sched, shifts.get(sched.shift_id), win.loc.timezone, day)
                    day_end = timeutil.local_to_utc(day + timedelta(days=1), time(0), win.loc.timezone)
                    for i, slot in enumerate(slots):
                        if slot > now:
                            continue
                        upper = slots[i + 1] if i + 1 < len(slots) else day_end
                        entry["due"] += 1
                        if any(slot - grace <= t < upper for t in times):
                            entry["done"] += 1
                        elif now > slot + grace:
                            entry["missed"] += 1
        out[eq.id] = entry
    due = sum(e["due"] for e in out.values())
    done = sum(e["done"] for e in out.values())
    return {"equipment": out, "due": due, "done": done, "missed": sum(e["missed"] for e in out.values()),
            "failed": sum(e["failed"] for e in out.values()), "percent": pct(done, due)}


def stock_snapshot(db: Session, scope: set[int] | None, location_id: int | None = None) -> dict:
    ids = {location_id} if location_id is not None else scope
    stmt = select(InventoryBalance, InventoryItem).join(InventoryItem, InventoryItem.id == InventoryBalance.item_id)
    if ids is not None:
        stmt = stmt.where(InventoryBalance.location_id.in_(ids))
    kinds = {k: {"qty": 0, "value": 0.0} for k in ("crockery", "smallware")}
    low = []
    for balance, item in db.execute(stmt).all():
        kinds[item.kind]["qty"] += balance.qty
        kinds[item.kind]["value"] += float(balance.qty * item.unit_cost) if item.unit_cost is not None else 0.0
        if item.active and balance.qty < item.min_level:
            low.append({"item_id": item.id, "code": item.code, "name": item.name, "kind": item.kind,
                        "location_id": balance.location_id, "qty": balance.qty, "min_level": item.min_level,
                        "target_level": item.target_level})
    return {"kinds": kinds, "low": low}


def movements(db: Session, wins: list[Win]) -> list[tuple[StockTransaction, date]]:
    out = []
    for win in wins:
        for txn in db.scalars(select(StockTransaction).where(
                StockTransaction.location_id == win.loc.id, StockTransaction.occurred_at >= win.start,
                StockTransaction.occurred_at < win.end).order_by(StockTransaction.id)):
            out.append((txn, timeutil.local_date(txn.occurred_at, win.loc.timezone)))
    return out


def breakage_in(db: Session, wins: list[Win]) -> list[tuple[BreakageIncident, date]]:
    out = []
    for win in wins:
        for inc in db.scalars(select(BreakageIncident).where(
                BreakageIncident.location_id == win.loc.id, BreakageIncident.occurred_at >= win.start,
                BreakageIncident.occurred_at < win.end, BreakageIncident.status != "rejected")
                .order_by(BreakageIncident.id)):
            out.append((inc, timeutil.local_date(inc.occurred_at, win.loc.timezone)))
    return out


def open_actions(db: Session, location_ids: set[int] | None) -> int:
    stmt = select(CorrectiveAction).join(TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id).where(
        CorrectiveAction.status != "resolved")
    if location_ids is not None:
        stmt = stmt.where(TemperatureReading.location_id.in_(location_ids))
    return len(db.scalars(stmt).all())
