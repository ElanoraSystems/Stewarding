from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import AttendanceRecord, Employee, EmployeeLocation, Location, Shift, ShiftAssignment, User
from ..pagination import row

router = APIRouter(prefix="/api/roster", tags=["roster"])


class ShiftIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    start_time: time
    end_time: time
    grace_minutes: int = Field(default=10, ge=0, le=120)
    break_minutes: int = Field(default=0, ge=0, le=240)
    overtime_after_minutes: int | None = Field(default=None, ge=0)
    active: bool = True


class AssignmentIn(BaseModel):
    employee_id: int
    shift_id: int
    location_id: int
    weekdays: list[int] = Field(min_length=1)
    valid_from: date


SHIFT_FIELDS = ("id", "name", "start_time", "end_time", "grace_minutes", "break_minutes",
                "overtime_after_minutes", "active")


@router.get("/shifts")
def list_shifts(user: User = Depends(require("roster.view")), db: Session = Depends(get_db)):
    return [row(s, *SHIFT_FIELDS) for s in db.scalars(select(Shift).order_by(Shift.start_time))]


@router.post("/shifts", status_code=201)
def create_shift(body: ShiftIn, user: User = Depends(require("roster.manage")), db: Session = Depends(get_db)):
    shift = Shift(**body.model_dump())
    db.add(shift)
    db.flush()
    audit(db, user, "shift.create", "shift", shift.id, None, body.model_dump(mode="json"))
    db.commit()
    return row(shift, *SHIFT_FIELDS)


@router.put("/shifts/{shift_id}")
def update_shift(shift_id: int, body: ShiftIn, user: User = Depends(require("roster.manage")),
                 db: Session = Depends(get_db)):
    shift = db.get(Shift, shift_id)
    if not shift:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shift not found")
    before = row(shift, *SHIFT_FIELDS)
    for key, value in body.model_dump().items():
        setattr(shift, key, value)
    audit(db, user, "shift.update", "shift", shift.id, {k: str(v) for k, v in before.items()},
          body.model_dump(mode="json"))
    db.commit()
    return row(shift, *SHIFT_FIELDS)


@router.get("/assignments")
def list_assignments(location_id: int | None = None, employee_id: int | None = None,
                     user: User = Depends(require("roster.view")), db: Session = Depends(get_db)):
    stmt = select(ShiftAssignment).where(or_(ShiftAssignment.valid_to.is_(None),
                                             ShiftAssignment.valid_to >= date.today()))
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(ShiftAssignment.location_id == location_id)
    elif allowed is not None:
        stmt = stmt.where(ShiftAssignment.location_id.in_(allowed))
    if employee_id is not None:
        stmt = stmt.where(ShiftAssignment.employee_id == employee_id)
    return [row(a, "id", "employee_id", "shift_id", "location_id", "weekday", "valid_from", "valid_to")
            for a in db.scalars(stmt.order_by(ShiftAssignment.location_id, ShiftAssignment.weekday))]


@router.post("/assignments", status_code=201)
def create_assignments(body: AssignmentIn, user: User = Depends(require("roster.manage")),
                       db: Session = Depends(get_db)):
    if any(d < 0 or d > 6 for d in body.weekdays):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weekdays must be 0 (Monday) to 6 (Sunday)")
    if not db.get(Shift, body.shift_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown shift")
    works_here = db.scalar(select(EmployeeLocation.employee_id).where(
        EmployeeLocation.employee_id == body.employee_id, EmployeeLocation.location_id == body.location_id))
    if works_here is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee is not assigned to that location")
    created = []
    try:
        for weekday in sorted(set(body.weekdays)):
            a = ShiftAssignment(employee_id=body.employee_id, shift_id=body.shift_id, location_id=body.location_id,
                                weekday=weekday, valid_from=body.valid_from)
            db.add(a)
            db.flush()
            created.append(a.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Assignment already exists") from None
    audit(db, user, "roster.assign", "shift_assignment", created[0], None, body.model_dump(mode="json"))
    db.commit()
    return {"ids": created}


@router.delete("/assignments/{assignment_id}")
def end_assignment(assignment_id: int, user: User = Depends(require("roster.manage")), db: Session = Depends(get_db)):
    a = db.get(ShiftAssignment, assignment_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    a.valid_to = date.today()
    audit(db, user, "roster.end", "shift_assignment", a.id, None, {"valid_to": a.valid_to.isoformat()})
    db.commit()
    return {"ok": True}


@router.get("/today")
def today(location_id: int, user: User = Depends(require("roster.view")), db: Session = Depends(get_db)):
    check_location(user, db, location_id)
    location = db.get(Location, location_id)
    now = timeutil.utc_now()
    day = timeutil.local_date(now, location.timezone)
    rows = db.execute(
        select(ShiftAssignment, Employee, Shift)
        .join(Employee, Employee.id == ShiftAssignment.employee_id)
        .join(Shift, Shift.id == ShiftAssignment.shift_id)
        .where(ShiftAssignment.location_id == location_id, ShiftAssignment.weekday == day.weekday(),
               ShiftAssignment.valid_from <= day, or_(ShiftAssignment.valid_to.is_(None),
                                                      ShiftAssignment.valid_to >= day),
               Employee.status == "active")
    ).all()
    attended = {r.employee_id: r for r in db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.location_id == location_id, AttendanceRecord.local_date == day))}
    return [{
        "employee_id": e.id, "name": e.full_name, "shift": s.name,
        "shift_start": s.start_time.isoformat(), "checked_in": e.id in attended,
        "late_minutes": attended[e.id].late_minutes if e.id in attended else 0,
        "on_duty": e.id in attended and attended[e.id].check_out_at is None,
    } for _, e, s in rows]
