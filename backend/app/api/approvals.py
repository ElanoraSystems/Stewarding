"""Everything waiting for an approver in one list: checklist tasks done and monitoring readings recorded."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, permissions_of, scoped_locations
from ..models import ChecklistInstance, ChecklistTask, ChecklistTemplate, Equipment, TemperatureReading, User
from ..services.monitoring import describe
from ..services.reference import user_names
from ..services.visibility import hidden_points, hidden_templates

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
LIMIT = 200


@router.get("")
def waiting_for_approval(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What this person may approve and has not yet: tasks (checklist approval) and readings (monitoring review), oldest first, never their own work."""
    perms, allowed, names = permissions_of(user), scoped_locations(user, db), user_names(db)
    tasks, readings = [], []
    if "checklist.verify" in perms:
        stmt = (select(ChecklistInstance, ChecklistTask, ChecklistTemplate)
                .join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
                .join(ChecklistTemplate, ChecklistTemplate.id == ChecklistTask.template_id)
                .where(ChecklistInstance.status == "pending_verification", ChecklistInstance.completed_by != user.id))
        if allowed is not None:
            stmt = stmt.where(ChecklistInstance.location_id.in_(allowed))
        if hidden := hidden_templates(db, user):
            stmt = stmt.where(ChecklistTemplate.id.not_in(hidden))
        for inst, task, template in db.execute(stmt.order_by(ChecklistInstance.completed_at, ChecklistInstance.id).limit(LIMIT)):
            tasks.append({"id": inst.id, "description": task.description, "checklist": template.name, "location_id": inst.location_id,
                          "local_date": inst.local_date.isoformat(), "done_by": names.get(inst.completed_by, ""), "done_at": inst.completed_at.isoformat() + "Z",
                          "comment": inst.comment, "has_photo": bool(inst.evidence_path)})
    if "temp.review" in perms:
        stmt = (select(TemperatureReading, Equipment).join(Equipment, Equipment.id == TemperatureReading.equipment_id)
                .where(TemperatureReading.reviewed_at.is_(None), TemperatureReading.rejected_at.is_(None), TemperatureReading.recorded_by != user.id))
        if allowed is not None:
            stmt = stmt.where(TemperatureReading.location_id.in_(allowed))
        if hidden := hidden_points(db, user):
            stmt = stmt.where(TemperatureReading.equipment_id.not_in(hidden))
        for reading, eq in db.execute(stmt.order_by(TemperatureReading.recorded_at, TemperatureReading.id).limit(LIMIT)):
            readings.append({"id": reading.id, "equipment": eq.name, "stage": reading.stage, "value": describe(reading), "passed": reading.passed,
                             "location_id": reading.location_id, "done_by": names.get(reading.recorded_by, ""), "done_at": reading.recorded_at.isoformat() + "Z",
                             "comment": reading.comment})
    return {"tasks": tasks, "readings": readings, "count": len(tasks) + len(readings)}
