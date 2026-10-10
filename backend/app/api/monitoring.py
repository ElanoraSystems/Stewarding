from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import (ApprovalRecord, CorrectiveAction, Employee, Equipment, EquipmentSchedule, TemperatureReading,
                      User)
from ..pagination import paginate, row
from ..permissions import MANAGER, SUPERVISOR
from ..services.notify import notify, recipients
from ..services.settings import get_setting
from ..services.monitoring import describe, due_checks, evaluate, failure_count, resolve_alerts, resolve_chain
from .equipment import serialize as serialize_equipment
from .uploads import is_valid_evidence

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

READING_FIELDS = ("id", "equipment_id", "schedule_id", "location_id", "recorded_at", "stage", "source", "parameter", "unit",
                  "value_type", "value", "reference", "min_limit", "max_limit", "passed", "recorded_by", "comment", "evidence_path", "retest_of_id",
                  "reviewed_by", "reviewed_at")
ACTION_FIELDS = ("id", "reading_id", "action", "taken_by", "taken_at", "retest_due_at", "status", "resolved_at",
                 "escalated_at")


class ReadingIn(BaseModel):
    equipment_id: int
    schedule_id: int
    value: Decimal = Field(ge=-100000, le=100000)
    reference: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=1000)
    evidence_path: str | None = None
    corrective_action: str | None = Field(default=None, max_length=1000)
    retest_of_id: int | None = None


class ActionIn(BaseModel):
    action: str = Field(min_length=5, max_length=1000)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=500)


def _equipment_for(db: Session, user: User, equipment_id: int) -> Equipment:
    eq = db.get(Equipment, equipment_id)
    if not eq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Monitoring point not found")
    check_location(user, db, eq.location_id)
    return eq


def _visible_equipment(db: Session, user: User, location_id: int | None) -> list[Equipment]:
    stmt = select(Equipment).where(Equipment.active.is_(True))
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(Equipment.location_id == location_id)
    elif allowed is not None:
        stmt = stmt.where(Equipment.location_id.in_(allowed))
    return list(db.scalars(stmt.order_by(Equipment.location_id, Equipment.code)))


def _latest_action(db: Session, reading_id: int) -> CorrectiveAction | None:
    return db.scalar(select(CorrectiveAction).where(CorrectiveAction.reading_id == reading_id)
                     .order_by(CorrectiveAction.id.desc()))


def _serialize_reading(db: Session, reading: TemperatureReading, names: dict[int, str]) -> dict:
    out = row(reading, *READING_FIELDS)
    out["recorded_by_name"] = names.get(reading.recorded_by)
    out["display"] = describe(reading.value, reading.value_type, reading.unit)
    action = _latest_action(db, reading.id)
    out["corrective_action"] = row(action, *ACTION_FIELDS) if action else None
    return out


def _names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(Employee.user_id, Employee.full_name).where(Employee.user_id.in_(user_ids))).all()
    return dict(rows)


@router.get("/equipment")
def equipment_for_recording(location_id: int | None = None, user: User = Depends(require("temp.view")),
                            db: Session = Depends(get_db)):
    return [serialize_equipment(db, eq) for eq in _visible_equipment(db, user, location_id)]


@router.get("/due")
def due(location_id: int | None = None, user: User = Depends(require("temp.view")), db: Session = Depends(get_db)):
    return due_checks(db, _visible_equipment(db, user, location_id), timeutil.utc_now())


@router.post("/readings", status_code=201)
def record_reading(body: ReadingIn, user: User = Depends(require("temp.record")), db: Session = Depends(get_db)):
    eq = _equipment_for(db, user, body.equipment_id)
    sched = db.get(EquipmentSchedule, body.schedule_id)
    if not sched or sched.equipment_id != eq.id or not sched.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown check for this monitoring point")
    if sched.value_type == "number" and sched.min_value is None and sched.max_value is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Limits are not configured for this check")
    if sched.value_type == "yes_no" and body.value not in (0, 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Answer yes or no")
    reference = (body.reference or "").strip() or None
    if sched.require_reference and reference is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter the batch, lot or product reference for this check")
    if body.evidence_path and not is_valid_evidence(body.evidence_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown evidence file")

    original_action = None
    if body.retest_of_id is not None:
        original = db.get(TemperatureReading, body.retest_of_id)
        if not original or original.equipment_id != eq.id or original.schedule_id != sched.id or original.passed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A retest must refer to a failed reading of the same check")
        if db.scalar(select(TemperatureReading.id).where(TemperatureReading.retest_of_id == original.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "This reading has already been retested")
        original_action = _latest_action(db, original.id)
        if not original_action or original_action.status != "retest_due":
            raise HTTPException(status.HTTP_409_CONFLICT, "Record the corrective action before retesting")

    now = timeutil.utc_now()
    value = body.value.quantize(Decimal("0.01"))
    passed = value == 1 if sched.value_type == "yes_no" else evaluate(value, sched.min_value, sched.max_value)
    reading = TemperatureReading(
        equipment_id=eq.id, schedule_id=sched.id, location_id=eq.location_id, recorded_at=now, stage=sched.stage,
        source=sched.source, parameter=sched.parameter, unit=sched.unit, value_type=sched.value_type, value=value,
        reference=reference, min_limit=sched.min_value, max_limit=sched.max_value, passed=passed,
        recorded_by=user.id, comment=body.comment, evidence_path=body.evidence_path, retest_of_id=body.retest_of_id)
    db.add(reading)
    db.flush()

    if original_action and passed:
        resolve_chain(db, reading, now)
    elif original_action:
        original_action.status = "retest_failed"
    if not passed:
        _open_failure(db, user, eq, reading, body.corrective_action, now)
    db.commit()
    return _serialize_reading(db, reading, _names(db, {reading.recorded_by}))


def _open_failure(db: Session, user: User, eq: Equipment, reading: TemperatureReading, text: str | None,
                  now: datetime) -> None:
    has_text = bool(text and len(text.strip()) >= 5)
    db.add(CorrectiveAction(
        reading_id=reading.id, action=text.strip() if has_text else "", taken_by=user.id,
        status="retest_due" if has_text else "action_required",
        retest_due_at=now + timedelta(minutes=get_setting(db, "temp.retest_minutes")) if has_text else None))
    limits = "Answered No" if reading.value_type == "yes_no" else f"Limits {reading.min_limit or '-'} to {reading.max_limit or '-'} {reading.unit or ''}".strip()
    notify(db, recipients(db, eq.location_id, SUPERVISOR, MANAGER), "monitoring_failed",
           f"Failed check: {eq.name} ({reading.stage}) {describe(reading.value, reading.value_type, reading.unit)}",
           key=f"temp_fail:{reading.id}", body=f"{limits}. Corrective action and retest required.",
           priority="critical", location_id=eq.location_id, link="/monitoring", requires_ack=True)
    if failure_count(db, eq.id, now) >= get_setting(db, "temp.repeat_failure_count"):
        notify(db, recipients(db, eq.location_id, MANAGER, SUPERVISOR), "equipment_maintenance",
               f"Repeated failures: {eq.name} needs review",
               key=f"maint:{eq.id}:{now.date().isoformat()}", priority="high", location_id=eq.location_id,
               link="/equipment", requires_ack=True)


@router.get("/readings")
def list_readings(equipment_id: int | None = None, location_id: int | None = None, date_from: date | None = None,
                  date_to: date | None = None, passed: bool | None = None, page: int = 1, size: int = 25,
                  user: User = Depends(require("temp.view")), db: Session = Depends(get_db)):
    stmt = select(TemperatureReading)
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(TemperatureReading.location_id == location_id)
    elif allowed is not None:
        stmt = stmt.where(TemperatureReading.location_id.in_(allowed))
    if equipment_id is not None:
        stmt = stmt.where(TemperatureReading.equipment_id == equipment_id)
    if passed is not None:
        stmt = stmt.where(TemperatureReading.passed.is_(passed))
    if date_from:
        stmt = stmt.where(TemperatureReading.recorded_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(TemperatureReading.recorded_at < datetime.combine(date_to + timedelta(days=1),
                                                                            datetime.min.time()))
    total, rows = paginate(db, stmt.order_by(TemperatureReading.recorded_at.desc()), page, size)
    readings = [r[0] for r in rows]
    names = _names(db, {r.recorded_by for r in readings})
    return {"total": total, "items": [_serialize_reading(db, r, names) for r in readings]}


@router.post("/readings/{reading_id}/review")
def review_reading(reading_id: int, user: User = Depends(require("temp.review")), db: Session = Depends(get_db)):
    reading = db.get(TemperatureReading, reading_id)
    if not reading:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reading not found")
    check_location(user, db, reading.location_id)
    if reading.recorded_by == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot review your own reading")
    if reading.reviewed_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reading was already reviewed")
    reading.reviewed_by, reading.reviewed_at = user.id, timeutil.utc_now()
    audit(db, user, "monitoring.review", "temperature_reading", reading.id)
    db.commit()
    return _serialize_reading(db, reading, _names(db, {reading.recorded_by}))


@router.get("/corrective-actions")
def list_actions(action_status: str | None = Query(None, alias="status"), location_id: int | None = None,
                 user: User = Depends(require("temp.view")), db: Session = Depends(get_db)):
    stmt = select(CorrectiveAction, TemperatureReading).join(
        TemperatureReading, TemperatureReading.id == CorrectiveAction.reading_id)
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(TemperatureReading.location_id == location_id)
    elif allowed is not None:
        stmt = stmt.where(TemperatureReading.location_id.in_(allowed))
    if action_status:
        stmt = stmt.where(CorrectiveAction.status == action_status)
    items = db.execute(stmt.order_by(CorrectiveAction.id.desc()).limit(200)).all()
    return [{**row(a, *ACTION_FIELDS), "equipment_id": r.equipment_id, "stage": r.stage, "display": describe(r.value, r.value_type, r.unit),
             "recorded_at": row(r, "recorded_at")["recorded_at"], "location_id": r.location_id} for a, r in items]


def _action_for(db: Session, user: User, action_id: int) -> tuple[CorrectiveAction, TemperatureReading]:
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Corrective action not found")
    reading = db.get(TemperatureReading, action.reading_id)
    check_location(user, db, reading.location_id)
    return action, reading


@router.post("/corrective-actions/{action_id}/action")
def record_action(action_id: int, body: ActionIn, user: User = Depends(require("temp.record")),
                  db: Session = Depends(get_db)):
    action, _ = _action_for(db, user, action_id)
    if action.status != "action_required":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Action is {action.status}")
    now = timeutil.utc_now()
    action.action, action.taken_by, action.taken_at = body.action.strip(), user.id, now
    action.status = "retest_due"
    action.retest_due_at = now + timedelta(minutes=get_setting(db, "temp.retest_minutes"))
    db.commit()
    return row(action, *ACTION_FIELDS)


@router.post("/corrective-actions/{action_id}/decision")
def decide(action_id: int, body: DecisionIn, user: User = Depends(require("temp.review")),
           db: Session = Depends(get_db)):
    action, reading = _action_for(db, user, action_id)
    if action.taken_by == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot approve your own corrective action")
    if action.status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Action is already resolved")
    now = timeutil.utc_now()
    if body.decision == "approve":
        action.status, action.resolved_at = "resolved", now
        resolve_alerts(db, reading.id, now)
    else:
        if not (body.note and body.note.strip()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A note is required when rejecting")
        action.status, action.retest_due_at = "action_required", None
        notify(db, [action.taken_by], "corrective_action_rejected", "Corrective action rejected - redo",
               key=f"reject_action:{action.id}:{now.isoformat()}", body=body.note, priority="high",
               location_id=reading.location_id, link="/monitoring")
    db.add(ApprovalRecord(subject_type="corrective_action", subject_id=action.id, decision=body.decision,
                          decided_by=user.id, reason=body.note))
    audit(db, user, f"monitoring.action_{body.decision}", "corrective_action", action.id, None, {"note": body.note})
    db.commit()
    return row(action, *ACTION_FIELDS)
