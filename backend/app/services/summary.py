from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (AttendanceRecord, BreakageIncident, ChecklistInstance, ChecklistTask, CorrectiveAction, Employee,
                      Equipment, InventoryBalance, InventoryItem, InventoryTransfer, Location, TemperatureReading)
from .checklists import OPEN
from .settings import get_setting
from .monitoring import CLOSED_ACTIONS, describe, due_checks
from .reference import employee_names, user_names

URGENCY_RANK = {"critical": 0, "high": 1, "normal": 2}


def _minutes(now: datetime, since: datetime | None) -> int:
    return max(0, int((now - since).total_seconds() // 60)) if since else 0


def pending_items(db: Session, location_ids: set[int] | None, now: datetime) -> list[dict]:
    """Everything outstanding right now, with location, urgency, responsible person and overdue minutes."""
    locations = {loc.id: loc.name for loc in db.scalars(select(Location)) if location_ids is None or loc.id in location_ids}
    names, by_user = employee_names(db), user_names(db)
    items: list[dict] = []

    def add(category, loc_id, urgency, responsible, description, since, link):
        items.append({"category": category, "location_id": loc_id, "location": locations[loc_id], "urgency": urgency,
                      "responsible": responsible, "description": description,
                      "overdue_minutes": _minutes(now, since), "link": link})

    rows = db.execute(
        select(ChecklistInstance, ChecklistTask).join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
        .where(ChecklistInstance.location_id.in_(locations),
               ((ChecklistInstance.status.in_(OPEN + ("overdue", "failed"))) & (ChecklistInstance.due_at < now))
               | (ChecklistInstance.status == "pending_verification"))).all()
    for inst, task in rows:
        if inst.status == "pending_verification":
            add("verification", inst.location_id, "normal", "Supervisor", f"Verify: {task.description}",
                inst.completed_at, "/checklists")
        else:
            urgency = "high" if task.priority in ("high", "critical") else "normal"
            who = names.get(inst.assigned_employee_id) or f"Unassigned ({task.assigned_role or 'steward'})"
            add("overdue_task", inst.location_id, urgency, who, task.description, inst.due_at, "/checklists")

    equipment = list(db.scalars(select(Equipment).where(Equipment.location_id.in_(locations), Equipment.active.is_(True))))
    sup_names = {eq.id: names.get(eq.supervisor_id, "Supervisor") for eq in equipment}
    for check in due_checks(db, equipment, now):
        if check["status"] == "overdue":
            slot = datetime.fromisoformat(check["slot_at"].rstrip("Z"))
            add("monitoring_check", check["location_id"], "critical", sup_names[check["equipment_id"]],
                f"Check overdue: {check['equipment']} ({check['stage']})", slot, "/monitoring")

    for action, reading in db.execute(
            select(CorrectiveAction, TemperatureReading).join(TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id)
            .where(TemperatureReading.location_id.in_(locations), CorrectiveAction.status.not_in(CLOSED_ACTIONS))).all():
        add("corrective_action", reading.location_id, "critical", by_user.get(action.taken_by, "Supervisor"),
            f"Failed reading {describe(reading)} ({reading.stage}) - {action.status.replace('_', ' ')}",
            reading.recorded_at, "/monitoring")

    cutoff = now - timedelta(days=14)
    for loc_id, count, oldest in db.execute(
            select(TemperatureReading.location_id, func.count(), func.min(TemperatureReading.recorded_at))
            .where(TemperatureReading.location_id.in_(locations), TemperatureReading.reviewed_at.is_(None), TemperatureReading.rejected_at.is_(None),
                   TemperatureReading.retest_of_id.is_(None), TemperatureReading.recorded_at >= cutoff)
            .group_by(TemperatureReading.location_id)):
        add("monitoring_review", loc_id, "normal", "Supervisor or manager", f"{count} monitoring reading(s) awaiting approval",
            oldest, "/monitoring")

    for incident in db.scalars(select(BreakageIncident).where(
            BreakageIncident.location_id.in_(locations), BreakageIncident.status.in_(("reported", "pending_approval")))):
        add("breakage", incident.location_id, "high", "Manager" if incident.status == "pending_approval" else "Supervisor",
            f"{incident.code} {incident.status.replace('_', ' ')}", incident.occurred_at, "/breakage")

    for transfer in db.scalars(select(InventoryTransfer).where(InventoryTransfer.status == "requested",
                                                               InventoryTransfer.from_location_id.in_(locations))):
        add("transfer", transfer.from_location_id, "normal", "Manager", f"Transfer #{transfer.id} awaiting approval",
            transfer.requested_at, "/stock-movements")

    hours = get_setting(db, "attendance.missed_checkout_hours")
    for rec in db.scalars(select(AttendanceRecord).where(AttendanceRecord.location_id.in_(locations),
                                                         AttendanceRecord.open_flag == 1)):
        if _minutes(now, rec.check_in_at) > hours * 60:
            add("attendance", rec.location_id, "high", names.get(rec.employee_id, "Employee"), "Missed check-out",
                rec.check_in_at, "/attendance")

    for balance, item in db.execute(
            select(InventoryBalance, InventoryItem).join(InventoryItem, InventoryItem.id == InventoryBalance.item_id)
            .where(InventoryBalance.location_id.in_(locations), InventoryItem.active.is_(True),
                   InventoryBalance.qty < InventoryItem.min_level)).all():
        add("low_stock", balance.location_id, "normal", "Supervisor",
            f"Low stock: {item.name} ({balance.qty} of minimum {item.min_level})", None, "/inventory")

    return sorted(items, key=lambda i: (URGENCY_RANK[i["urgency"]], i["location"], -i["overdue_minutes"]))


def grouped(items: list[dict]) -> dict:
    by_location: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = by_location.setdefault(item["location"], {"critical": 0, "high": 0, "normal": 0})
        bucket[item["urgency"]] += 1
    return {"total": len(items), "by_location": by_location,
            "by_urgency": {u: sum(1 for i in items if i["urgency"] == u) for u in URGENCY_RANK}}
