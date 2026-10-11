from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import (AbsenceRecord, AttendanceCorrection, AttendanceRecord, ChecklistInstance, ChecklistTask, Employee,
                      EmployeeLocation, Location, Shift, ShiftAssignment, User)
from ..pagination import iso, paginate, row
from ..security import verify_password
from ..services.checklists import DONE
from ..services.notify import notify

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

MISSED_CHECKOUT_HOURS = 16
FIELDS = ("id", "employee_id", "location_id", "shift_id", "local_date", "check_in_at", "check_out_at",
          "late_minutes", "payable_minutes", "overtime_minutes", "exception_reason")


class CheckInIn(BaseModel):
    location_id: int
    pin: str | None = None


class CheckOutIn(BaseModel):
    exception_reason: str | None = Field(default=None, max_length=500)


class CorrectionIn(BaseModel):
    field: Literal["check_in_at", "check_out_at"]
    new_value: datetime
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("new_value")
    @classmethod
    def _needs_offset(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("new_value must include a timezone offset")
        return v


MANUAL_DAYS_BACK = 62
MANUAL_PREFIX = "Manual entry by manager"


class ManualIn(BaseModel):
    employee_id: int
    location_id: int
    day: date
    check_in_time: time
    check_out_time: time
    reason: str = Field(min_length=5, max_length=500)


def _employee(user: User) -> Employee:
    if not user.employee:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No employee profile on this account")
    return user.employee


def _open_record(db: Session, emp: Employee) -> AttendanceRecord | None:
    return db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == emp.id,
                                                    AttendanceRecord.open_flag == 1))


def _pick_shift(db: Session, emp: Employee, location: Location, now: datetime) -> Shift | None:
    day = timeutil.local_date(now, location.timezone)
    candidates = db.scalars(
        select(Shift).join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(ShiftAssignment.employee_id == emp.id, ShiftAssignment.location_id == location.id,
               ShiftAssignment.weekday == day.weekday(), ShiftAssignment.valid_from <= day,
               or_(ShiftAssignment.valid_to.is_(None), ShiftAssignment.valid_to >= day), Shift.active.is_(True),
               Shift.kind == "work")
    ).all()
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs((now - timeutil.local_to_utc(day, s.start_time, location.timezone))
                                             .total_seconds()))


def incomplete_tasks(db: Session, user: User, record: AttendanceRecord) -> list[ChecklistInstance]:
    emp = user.employee
    unassigned = and_(ChecklistInstance.assigned_employee_id.is_(None),
                      ChecklistInstance.shift_key.in_((0, record.shift_id or 0)),
                      or_(ChecklistTask.assigned_role.is_(None), ChecklistTask.assigned_role == user.role.name))
    return db.scalars(
        select(ChecklistInstance).join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
        .where(ChecklistInstance.location_id == record.location_id, ChecklistInstance.local_date == record.local_date,
               ChecklistTask.mandatory_for_checkout.is_(True), ChecklistInstance.status.not_in(DONE),
               or_(ChecklistInstance.assigned_employee_id == emp.id, unassigned))
    ).all()


def _recompute(record: AttendanceRecord, shift: Shift | None) -> None:
    if not record.check_out_at:
        return
    elapsed = int((record.check_out_at - record.check_in_at).total_seconds() // 60)
    break_minutes = shift.break_minutes if shift else 0
    payable = max(0, elapsed - break_minutes)
    record.payable_minutes = payable
    if shift:
        scheduled = timeutil.shift_minutes(shift.start_time, shift.end_time) - break_minutes
        limit = shift.overtime_after_minutes if shift.overtime_after_minutes is not None else scheduled
        record.overtime_minutes = max(0, payable - limit)
    else:
        record.overtime_minutes = 0


def _serialize(record: AttendanceRecord, now: datetime, names: dict[int, str] | None = None) -> dict:
    out = row(record, *FIELDS)
    out["open"] = record.open_flag == 1
    out["missed_checkout"] = (record.open_flag == 1 and
                              (now - record.check_in_at).total_seconds() > MISSED_CHECKOUT_HOURS * 3600)
    if names is not None:
        out["employee_name"] = names.get(record.employee_id)
    return out


@router.post("/check-in", status_code=201)
def check_in(body: CheckInIn, user: User = Depends(require("attendance.self")), db: Session = Depends(get_db)):
    emp = _employee(user)
    check_location(user, db, body.location_id)
    location = db.get(Location, body.location_id)
    if not location.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Location is not active")
    if location.checkin_pin_hash and not (body.pin and verify_password(body.pin, location.checkin_pin_hash)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Location PIN is required and was not accepted")
    if _open_record(db, emp):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already checked in")
    now = timeutil.utc_now()
    shift = _pick_shift(db, emp, location, now)
    day = timeutil.local_date(now, location.timezone)
    late = 0
    if shift:
        minutes_after_start = int((now - timeutil.local_to_utc(day, shift.start_time, location.timezone))
                                  .total_seconds() // 60)
        late = minutes_after_start if minutes_after_start > shift.grace_minutes else 0
    record = AttendanceRecord(employee_id=emp.id, location_id=location.id, shift_id=shift.id if shift else None,
                              local_date=day, check_in_at=now, late_minutes=late, open_flag=1)
    try:
        db.add(record)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already checked in") from None
    db.commit()
    return _serialize(record, now)


@router.post("/check-out")
def check_out(body: CheckOutIn, user: User = Depends(require("attendance.self")), db: Session = Depends(get_db)):
    emp = _employee(user)
    record = _open_record(db, emp)
    if not record:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are not checked in")
    pending = incomplete_tasks(db, user, record)
    reason = (body.exception_reason or "").strip()
    if pending and len(reason) < 5:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={
            "message": "Mandatory tasks are incomplete; finish them or give an exception reason",
            "tasks": [{"id": t.id, "task_id": t.task_id} for t in pending]})
    now = timeutil.utc_now()
    record.check_out_at = now
    record.open_flag = None
    _recompute(record, db.get(Shift, record.shift_id) if record.shift_id else None)
    if pending:
        record.exception_reason = reason
        audit(db, user, "attendance.checkout_exception", "attendance_record", record.id, None,
              {"reason": reason, "incomplete_instance_ids": [t.id for t in pending]})
    db.commit()
    return _serialize(record, now)


@router.get("/me/status")
def my_status(user: User = Depends(require("attendance.self")), db: Session = Depends(get_db)):
    emp = _employee(user)
    now = timeutil.utc_now()
    record = _open_record(db, emp)
    out = {"checked_in": record is not None, "server_time": iso(now), "employee": emp.full_name,
           "employee_code": emp.employee_code, "record": None, "incomplete_task_count": 0}
    if record:
        out["record"] = _serialize(record, now)
        out["incomplete_task_count"] = len(incomplete_tasks(db, user, record))
        location = db.get(Location, record.location_id)
        out["location"] = {"id": location.id, "name": location.name, "timezone": location.timezone}
        if record.shift_id:
            out["shift"] = db.get(Shift, record.shift_id).name
    return out


@router.get("/mine")
def my_history(page: int = 1, size: int = 25, user: User = Depends(require("attendance.self")),
               db: Session = Depends(get_db)):
    emp = _employee(user)
    now = timeutil.utc_now()
    total, rows = paginate(db, select(AttendanceRecord).where(AttendanceRecord.employee_id == emp.id)
                           .order_by(AttendanceRecord.check_in_at.desc()), page, size)
    return {"total": total, "items": [_serialize(r[0], now) for r in rows]}


@router.get("")
def list_attendance(location_id: int | None = None, employee_id: int | None = None, date_from: date | None = None,
                    date_to: date | None = None, page: int = 1, size: int = 25,
                    user: User = Depends(require("attendance.view")), db: Session = Depends(get_db)):
    stmt = select(AttendanceRecord)
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(AttendanceRecord.location_id == location_id)
    elif allowed is not None:
        stmt = stmt.where(AttendanceRecord.location_id.in_(allowed))
    if employee_id is not None:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(AttendanceRecord.local_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceRecord.local_date <= date_to)
    total, rows = paginate(db, stmt.order_by(AttendanceRecord.check_in_at.desc()), page, size)
    now = timeutil.utc_now()
    ids = {r[0].employee_id for r in rows}
    names = dict(db.execute(select(Employee.id, Employee.full_name).where(Employee.id.in_(ids))).all()) if ids else {}
    return {"total": total, "items": [_serialize(r[0], now, names) for r in rows]}


@router.post("/manual", status_code=201)
def add_manual(body: ManualIn, user: User = Depends(require("attendance.correct")), db: Session = Depends(get_db)):
    """A manager records the punch in and out an employee missed; it counts as a present day like any other."""
    check_location(user, db, body.location_id)
    location = db.get(Location, body.location_id)
    emp = db.get(Employee, body.employee_id)
    works_here = emp and db.scalar(select(EmployeeLocation.employee_id).where(
        EmployeeLocation.employee_id == emp.id, EmployeeLocation.location_id == location.id))
    if not works_here or emp.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee is not active at this location")
    now = timeutil.utc_now()
    today = timeutil.local_date(now, location.timezone)
    if not (today - timedelta(days=MANUAL_DAYS_BACK) <= body.day <= today):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The date must be today or within the last {MANUAL_DAYS_BACK} days")
    check_in = timeutil.local_to_utc(body.day, body.check_in_time, location.timezone)
    check_out_day = body.day if body.check_out_time > body.check_in_time else body.day + timedelta(days=1)
    check_out = timeutil.local_to_utc(check_out_day, body.check_out_time, location.timezone)
    if body.check_out_time == body.check_in_time:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Check-out must be after check-in")
    if check_out > now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The check-out time is in the future")
    if (check_out - check_in) > timedelta(hours=20):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A shift cannot be longer than 20 hours")
    if db.scalar(select(AttendanceRecord.id).where(AttendanceRecord.employee_id == emp.id, AttendanceRecord.local_date == body.day)):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is already an attendance record that day; correct its times instead")
    if db.scalar(select(AbsenceRecord.id).where(AbsenceRecord.employee_id == emp.id, AbsenceRecord.local_date == body.day,
                                                AbsenceRecord.voided_at.is_(None))):
        raise HTTPException(status.HTTP_409_CONFLICT, "An absence or leave is recorded that day; cancel it first")
    shift = _pick_shift(db, emp, location, check_in)
    late = 0
    if shift:
        after_start = int((check_in - timeutil.local_to_utc(body.day, shift.start_time, location.timezone)).total_seconds() // 60)
        late = after_start if after_start > shift.grace_minutes else 0
    reason = " ".join(body.reason.split())
    record = AttendanceRecord(employee_id=emp.id, location_id=location.id, shift_id=shift.id if shift else None, local_date=body.day,
                              check_in_at=check_in, check_out_at=check_out, late_minutes=late, open_flag=None,
                              exception_reason=f"{MANUAL_PREFIX}: {reason}", verified_by=user.id)
    db.add(record)
    db.flush()
    _recompute(record, shift)
    for field, value in (("check_in_at", check_in), ("check_out_at", check_out)):
        db.add(AttendanceCorrection(attendance_id=record.id, corrected_by=user.id, field=field, old_value=None,
                                    new_value=iso(value), reason=f"Manual entry: {reason}"))
    audit(db, user, "attendance.manual", "attendance_record", record.id, None,
          {"employee_id": emp.id, "date": body.day.isoformat(), "check_in": iso(check_in), "check_out": iso(check_out), "reason": reason})
    if emp.user_id:
        notify(db, [emp.user_id], "attendance_manual", f"Attendance added for {body.day.strftime('%d %b %Y')}",
               key=f"manual_att:{record.id}", body=f"Your manager recorded your attendance: {reason}", location_id=location.id,
               link="/attendance")
    db.commit()
    return _serialize(record, now)


@router.post("/{attendance_id}/correct")
def correct(attendance_id: int, body: CorrectionIn, user: User = Depends(require("attendance.correct")),
            db: Session = Depends(get_db)):
    record = db.get(AttendanceRecord, attendance_id)
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attendance record not found")
    new_value = timeutil.aware_to_utc(body.new_value)
    old_value = getattr(record, body.field)
    check_in = new_value if body.field == "check_in_at" else record.check_in_at
    check_out = new_value if body.field == "check_out_at" else record.check_out_at
    if check_out and check_out <= check_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Check-out must be after check-in")
    db.add(AttendanceCorrection(attendance_id=record.id, corrected_by=user.id, field=body.field,
                                old_value=iso(old_value), new_value=iso(new_value), reason=body.reason))
    setattr(record, body.field, new_value)
    if body.field == "check_out_at":
        record.open_flag = None
    shift = db.get(Shift, record.shift_id) if record.shift_id else None
    _recompute(record, shift)
    audit(db, user, "attendance.correct", "attendance_record", record.id,
          {body.field: iso(old_value)}, {body.field: iso(new_value), "reason": body.reason})
    db.commit()
    return _serialize(record, timeutil.utc_now())
