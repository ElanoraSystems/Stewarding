from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import AbsenceRecord, AttendanceRecord, Employee, EmployeeLocation, Location, User
from ..pagination import paginate, row

router = APIRouter(prefix="/api/absences", tags=["absences"])

AbsenceType = Literal["absent", "sick_leave", "annual_leave", "unpaid_leave", "other_leave"]
PAST_DAYS = 31
FUTURE_DAYS = 366
FIELDS = ("id", "employee_id", "location_id", "local_date", "absence_type", "note", "recorded_by", "created_at",
          "voided_by", "voided_at", "void_reason")


class AbsenceIn(BaseModel):
    employee_id: int
    location_id: int
    day: date
    absence_type: AbsenceType
    note: str | None = Field(default=None, max_length=500)


class VoidIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


def _serialize(db: Session, record: AbsenceRecord) -> dict:
    out = row(record, *FIELDS)
    out["status"] = "void" if record.voided_at else "active"
    out["employee_name"] = db.scalar(select(Employee.full_name).where(Employee.id == record.employee_id))
    out["recorded_by_name"] = db.scalar(select(Employee.full_name).where(Employee.user_id == record.recorded_by))
    return out


@router.post("", status_code=201)
def record_absence(body: AbsenceIn, user: User = Depends(require("attendance.absence")), db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    emp = db.get(Employee, body.employee_id)
    works_here = emp and db.scalar(select(EmployeeLocation.employee_id).where(
        EmployeeLocation.employee_id == emp.id, EmployeeLocation.location_id == body.location_id))
    if not works_here or emp.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee is not active at this location")
    today = timeutil.local_date(timeutil.utc_now(), db.get(Location, body.location_id).timezone)
    if not (today - timedelta(days=PAST_DAYS) <= body.day <= today + timedelta(days=FUTURE_DAYS)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The date must be within {PAST_DAYS} days back and {FUTURE_DAYS} days ahead")
    if db.scalar(select(AttendanceRecord.id).where(AttendanceRecord.employee_id == emp.id, AttendanceRecord.local_date == body.day)):
        raise HTTPException(status.HTTP_409_CONFLICT, "The employee checked in on that day, so they cannot be marked absent")
    record = AbsenceRecord(employee_id=emp.id, location_id=body.location_id, local_date=body.day,
                           absence_type=body.absence_type, note=body.note, recorded_by=user.id)
    try:
        db.add(record)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An absence or leave is already recorded for that employee and day") from None
    audit(db, user, "absence.record", "absence_record", record.id, None,
          {"employee_id": emp.id, "date": body.day.isoformat(), "type": body.absence_type})
    db.commit()
    return _serialize(db, record)


@router.get("/mine")
def my_absences(user: User = Depends(require("attendance.self")), db: Session = Depends(get_db)):
    if not user.employee:
        return []
    stmt = select(AbsenceRecord).where(AbsenceRecord.employee_id == user.employee.id, AbsenceRecord.voided_at.is_(None))
    return [_serialize(db, r) for r in db.scalars(stmt.order_by(AbsenceRecord.local_date.desc()).limit(50))]


@router.get("")
def list_absences(location_id: int | None = None, employee_id: int | None = None, date_from: date | None = None,
                  date_to: date | None = None, include_void: bool = False, page: int = 1, size: int = 25,
                  user: User = Depends(require("attendance.view")), db: Session = Depends(get_db)):
    stmt = select(AbsenceRecord)
    scope = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(AbsenceRecord.location_id == location_id)
    elif scope is not None:
        stmt = stmt.where(AbsenceRecord.location_id.in_(scope))
    if employee_id is not None:
        stmt = stmt.where(AbsenceRecord.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(AbsenceRecord.local_date >= date_from)
    if date_to:
        stmt = stmt.where(AbsenceRecord.local_date <= date_to)
    if not include_void:
        stmt = stmt.where(AbsenceRecord.voided_at.is_(None))
    total, rows = paginate(db, stmt.order_by(AbsenceRecord.local_date.desc(), AbsenceRecord.id.desc()), page, size)
    return {"total": total, "items": [_serialize(db, r[0]) for r in rows]}


@router.post("/{absence_id}/void")
def void_absence(absence_id: int, body: VoidIn, user: User = Depends(require("attendance.absence")),
                 db: Session = Depends(get_db)):
    """Cancels a recorded absence; the row stays for the history and the day can be recorded again."""
    record = db.get(AbsenceRecord, absence_id)
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    check_location(user, db, record.location_id)
    if record.voided_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Record is already void")
    record.voided_by, record.voided_at, record.void_reason = user.id, timeutil.utc_now(), body.reason
    audit(db, user, "absence.void", "absence_record", record.id, {"type": record.absence_type}, {"reason": body.reason})
    db.commit()
    return _serialize(db, record)
