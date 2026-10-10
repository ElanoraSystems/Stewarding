from datetime import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import Employee, Equipment, EquipmentSchedule, Location, Shift, User
from ..pagination import row
from ..services.settings import get_setting
from ..services.monitoring import failure_count
from ..services.monitoring_templates import BY_KEY, TEMPLATES
from .. import timeutil

router = APIRouter(prefix="/api/equipment", tags=["monitoring points"])

EQUIPMENT_FIELDS = ("id", "code", "name", "kind", "location_id", "manufacturer", "model", "serial_number",
                    "supervisor_id", "status", "procedure_reference", "maintenance_notes", "active")
SCHEDULE_FIELDS = ("id", "equipment_id", "stage", "parameter", "unit", "value_type", "require_reference", "source", "timing",
                   "time_of_day", "interval_minutes", "weekdays", "day_of_month", "shift_id", "min_value", "max_value", "active")


class EquipmentIn(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(min_length=2, max_length=40)
    location_id: int
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    supervisor_id: int | None = None
    status: str = Field(default="operational", pattern="^(operational|attention|out_of_service)$")
    procedure_reference: str | None = Field(default=None, max_length=300)
    maintenance_notes: str | None = None


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    supervisor_id: int | None = None
    status: str | None = Field(default=None, pattern="^(operational|attention|out_of_service)$")
    procedure_reference: str | None = Field(default=None, max_length=300)
    maintenance_notes: str | None = None
    active: bool | None = None


class ScheduleIn(BaseModel):
    stage: str = Field(min_length=2, max_length=60)
    parameter: str = Field(default="Temperature", min_length=2, max_length=60)
    unit: str | None = Field(default="°C", max_length=20)
    value_type: str = Field(default="number", pattern="^(number|yes_no)$")
    require_reference: bool = False
    source: str = Field(default="machine_display", pattern="^(machine_display|independent_probe)$")
    timing: str = Field(pattern="^(startup|interval|checkpoint)$")
    time_of_day: time | None = None
    interval_minutes: int | None = Field(default=None, gt=0, le=1440)
    weekdays: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    shift_id: int | None = None
    min_value: Decimal | None = Field(default=None, ge=-100000, le=100000)
    max_value: Decimal | None = Field(default=None, ge=-100000, le=100000)
    active: bool = True

    @model_validator(mode="after")
    def _check(self):
        if self.value_type == "yes_no":
            self.min_value = self.max_value = self.unit = None
        elif self.min_value is None and self.max_value is None:
            raise ValueError("Set a minimum or a maximum limit")
        if None not in (self.min_value, self.max_value) and self.min_value > self.max_value:
            raise ValueError("Minimum limit cannot exceed the maximum limit")
        if self.timing == "interval" and not self.interval_minutes:
            raise ValueError("Interval monitoring needs interval_minutes")
        if self.weekdays is not None and any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("Weekdays must be 0 (Monday) to 6 (Sunday)")
        return self


def _schedule_values(body: ScheduleIn) -> dict:
    values = body.model_dump()
    values["weekdays"] = ",".join(str(d) for d in sorted(set(body.weekdays))) if body.weekdays else None
    return values


def schedule_out(s: EquipmentSchedule) -> dict:
    out = row(s, *SCHEDULE_FIELDS)
    out["weekdays"] = [int(d) for d in s.weekdays.split(",")] if s.weekdays else []
    return out


def _get(db: Session, user: User, equipment_id: int) -> Equipment:
    eq = db.get(Equipment, equipment_id)
    if not eq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Monitoring point not found")
    check_location(user, db, eq.location_id)
    return eq


def serialize(db: Session, eq: Equipment) -> dict:
    schedules = db.scalars(select(EquipmentSchedule).where(EquipmentSchedule.equipment_id == eq.id)
                           .order_by(EquipmentSchedule.id))
    failures = failure_count(db, eq.id, timeutil.utc_now())
    return {**row(eq, *EQUIPMENT_FIELDS), "schedules": [schedule_out(s) for s in schedules],
            "recent_failures": failures,
            "needs_attention": eq.status != "operational" or failures >= get_setting(db, "temp.repeat_failure_count")}


def _validate_refs(db: Session, supervisor_id: int | None, shift_id: int | None = None) -> None:
    if supervisor_id is not None and not db.get(Employee, supervisor_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown supervisor")
    if shift_id is not None and not db.get(Shift, shift_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown shift")


@router.get("")
def list_equipment(location_id: int | None = None, kind: str | None = None,
                   user: User = Depends(require("equipment.view")), db: Session = Depends(get_db)):
    stmt = select(Equipment)
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(Equipment.location_id == location_id)
    elif allowed is not None:
        stmt = stmt.where(Equipment.location_id.in_(allowed))
    if kind:
        stmt = stmt.where(Equipment.kind == kind)
    return [serialize(db, eq) for eq in db.scalars(stmt.order_by(Equipment.location_id, Equipment.code))]


@router.post("", status_code=201)
def create_equipment(body: EquipmentIn, user: User = Depends(require("equipment.manage")),
                     db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    _validate_refs(db, body.supervisor_id)
    if db.scalar(select(Equipment.id).where(Equipment.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Monitoring point code already exists")
    eq = Equipment(**body.model_dump())
    db.add(eq)
    db.flush()
    audit(db, user, "equipment.create", "equipment", eq.id, None, body.model_dump())
    db.commit()
    return serialize(db, eq)


@router.put("/{equipment_id}")
def update_equipment(equipment_id: int, body: EquipmentUpdate, user: User = Depends(require("equipment.manage")),
                     db: Session = Depends(get_db)):
    eq = _get(db, user, equipment_id)
    data = body.model_dump(exclude_unset=True)
    _validate_refs(db, data.get("supervisor_id"))
    before = {k: getattr(eq, k) for k in data}
    for key, value in data.items():
        setattr(eq, key, value)
    audit(db, user, "equipment.update", "equipment", eq.id, before, data)
    db.commit()
    return serialize(db, eq)


def _schedule_snapshot(s: EquipmentSchedule) -> dict:
    return {k: str(v) if v is not None else None for k, v in schedule_out(s).items()}


@router.post("/{equipment_id}/schedules", status_code=201)
def create_schedule(equipment_id: int, body: ScheduleIn, user: User = Depends(require("equipment.manage")),
                    db: Session = Depends(get_db)):
    eq = _get(db, user, equipment_id)
    _validate_refs(db, None, body.shift_id)
    sched = EquipmentSchedule(equipment_id=eq.id, **_schedule_values(body))
    db.add(sched)
    db.flush()
    audit(db, user, "equipment.schedule_create", "equipment_schedule", sched.id, None, _schedule_snapshot(sched))
    db.commit()
    return schedule_out(sched)


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, body: ScheduleIn, user: User = Depends(require("equipment.manage")),
                    db: Session = Depends(get_db)):
    sched = db.get(EquipmentSchedule, schedule_id)
    if not sched:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    _get(db, user, sched.equipment_id)
    _validate_refs(db, None, body.shift_id)
    before = _schedule_snapshot(sched)
    for key, value in _schedule_values(body).items():
        setattr(sched, key, value)
    audit(db, user, "equipment.schedule_update", "equipment_schedule", sched.id, before, _schedule_snapshot(sched))
    db.commit()
    return schedule_out(sched)


class FromTemplateIn(BaseModel):
    template: str
    location_id: int
    name: str | None = Field(default=None, min_length=2, max_length=120)
    supervisor_id: int | None = None


def _next_code(db: Session, prefix: str, location_code: str) -> str:
    n = 1
    while db.scalar(select(Equipment.id).where(Equipment.code == f"{prefix}-{location_code}-{n}")):
        n += 1
    return f"{prefix}-{location_code}-{n}"


@router.get("/templates")
def list_templates(user: User = Depends(require("equipment.manage"))):
    return [{"key": t["key"], "name": t["name"], "type": t["type"], "checks": [
        {"stage": c["stage"], "parameter": c["parameter"], "unit": c["unit"], "value_type": c["value_type"],
         "min_value": c.get("min_value"), "max_value": c.get("max_value"), "timing": c["timing"]} for c in t["checks"]]}
        for t in TEMPLATES]


@router.post("/from-template", status_code=201)
def create_from_template(body: FromTemplateIn, user: User = Depends(require("equipment.manage")),
                         db: Session = Depends(get_db)):
    preset = BY_KEY.get(body.template)
    if not preset:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown template")
    check_location(user, db, body.location_id)
    _validate_refs(db, body.supervisor_id)
    location = db.get(Location, body.location_id)
    eq = Equipment(code=_next_code(db, preset["prefix"], location.code), name=body.name or f"{location.name} {preset['name']}",
                   kind=preset["type"], location_id=location.id, supervisor_id=body.supervisor_id)
    db.add(eq)
    db.flush()
    for check in preset["checks"]:
        weekdays = check.get("weekdays")
        db.add(EquipmentSchedule(equipment_id=eq.id, **{**check, "weekdays": weekdays}))
    audit(db, user, "equipment.create", "equipment", eq.id, None, {"template": body.template, "code": eq.code})
    db.commit()
    return serialize(db, eq)
