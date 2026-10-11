import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import asc, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import (AttendanceRecord, ChecklistInstance, Employee, EmployeeLocation, Location, Role, User)
from ..pagination import paginate, row
from ..security import hash_password

router = APIRouter(prefix="/api/employees", tags=["employees"])

RoleName = Literal["manager", "supervisor", "steward"]
SORTABLE = {"full_name", "employee_code", "job_title", "status", "date_joined"}
PRIVATE = ("phone", "email", "emergency_contact", "date_joined", "weekly_schedule", "photo_path")


PHONE_RE = re.compile(r"^[0-9+()\-.\s]{5,40}$")
CODE_RE = re.compile(r"^[A-Za-z0-9._-]+$")
FIRST_DAY = date(2000, 1, 1)


def _text(value: str | None) -> str | None:
    return " ".join(value.split()) or None if isinstance(value, str) else value


def _name(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = " ".join(value.split())
    if len(cleaned) < 2:
        raise ValueError("Enter at least 2 characters")
    return cleaned


def _phone(value: str | None) -> str | None:
    value = _text(value)
    if value and not PHONE_RE.match(value):
        raise ValueError("Phone may contain digits, spaces, + ( ) - and .")
    return value


def _joined(value: date | None) -> date | None:
    if value and not (FIRST_DAY <= value <= date.today() + timedelta(days=366)):
        raise ValueError("The joining date is out of range")
    return value


def _password(value: str) -> str:
    classes = sum(any(check(c) for c in value) for check in (str.islower, str.isupper, str.isdigit, lambda c: not c.isalnum()))
    if classes < 2:
        raise ValueError("Use at least two kinds of characters: letters, numbers or symbols")
    return value


class EmployeeIn(BaseModel):
    employee_code: str = Field(min_length=2, max_length=20, pattern=CODE_RE.pattern)
    full_name: str = Field(min_length=2, max_length=120)
    job_title: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: RoleName
    phone: str | None = Field(default=None, max_length=40)
    emergency_contact: str | None = Field(default=None, max_length=200)
    date_joined: date | None = None
    supervisor_id: int | None = None
    location_ids: list[int] = Field(min_length=1)
    weekly_schedule: dict | None = None

    _names = field_validator("full_name", "job_title")(_name)
    _phone = field_validator("phone")(_phone)
    _contact = field_validator("emergency_contact")(_text)
    _joined = field_validator("date_joined")(_joined)
    _password = field_validator("password")(_password)


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, min_length=2, max_length=80)
    role: RoleName | None = None
    phone: str | None = Field(default=None, max_length=40)
    emergency_contact: str | None = Field(default=None, max_length=200)
    date_joined: date | None = None
    supervisor_id: int | None = None
    location_ids: list[int] | None = Field(default=None, min_length=1)
    weekly_schedule: dict | None = None

    _names = field_validator("full_name", "job_title")(_name)
    _phone = field_validator("phone")(_phone)
    _contact = field_validator("emergency_contact")(_text)
    _joined = field_validator("date_joined")(_joined)


def _location_ids(emp: Employee) -> list[int]:
    return sorted(el.location_id for el in emp.locations)


def serialize(emp: Employee, full: bool) -> dict:
    out = row(emp, "id", "employee_code", "full_name", "job_title", "status", "supervisor_id")
    out["location_ids"] = _location_ids(emp)
    out["role"] = emp.user.role.name if emp.user else None
    if full:
        out.update(row(emp, *PRIVATE))
    return out


def _snapshot(emp: Employee) -> dict:
    return {"full_name": emp.full_name, "job_title": emp.job_title, "supervisor_id": emp.supervisor_id,
            "location_ids": _location_ids(emp), "role": emp.user.role.name if emp.user else None}


def _get_visible(db: Session, user: User, employee_id: int) -> Employee:
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    allowed = scoped_locations(user, db)
    if allowed is not None and not (set(_location_ids(emp)) & allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Employee is outside your locations")
    return emp


def _validate_refs(db: Session, location_ids: list[int], supervisor_id: int | None) -> None:
    found = set(db.scalars(select(Location.id).where(Location.id.in_(location_ids))))
    if found != set(location_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown location")
    if supervisor_id is not None and not db.get(Employee, supervisor_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown supervisor")


@router.get("")
def list_employees(
    search: str | None = None, status_: str | None = Query(None, alias="status"), location_id: int | None = None,
    sort: str = "full_name", direction: Literal["asc", "desc"] = Query("asc", alias="dir"),
    page: int = 1, size: int = 25,
    user: User = Depends(require("employee.view")), db: Session = Depends(get_db),
):
    stmt = select(Employee)
    allowed = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
    if allowed is not None or location_id is not None:
        subq = select(EmployeeLocation.employee_id)
        if allowed is not None:
            subq = subq.where(EmployeeLocation.location_id.in_(allowed))
        if location_id is not None:
            subq = subq.where(EmployeeLocation.location_id == location_id)
        stmt = stmt.where(Employee.id.in_(subq))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like), Employee.employee_code.ilike(like)))
    if status_:
        stmt = stmt.where(Employee.status == status_)
    column = getattr(Employee, sort if sort in SORTABLE else "full_name")
    stmt = stmt.order_by(asc(column) if direction == "asc" else desc(column), Employee.id)
    total, rows = paginate(db, stmt, page, size)
    full = user.role.name == "manager"
    return {"total": total, "page": page, "items": [serialize(r[0], full) for r in rows]}


@router.post("", status_code=201)
def create_employee(body: EmployeeIn, user: User = Depends(require("employee.manage")), db: Session = Depends(get_db)):
    _validate_refs(db, body.location_ids, body.supervisor_id)
    role = db.scalar(select(Role).where(Role.name == body.role))
    try:
        account = User(email=str(body.email).lower(), password_hash=hash_password(body.password), role_id=role.id)
        db.add(account)
        db.flush()
        emp = Employee(
            employee_code=body.employee_code, user_id=account.id, full_name=body.full_name, job_title=body.job_title,
            email=str(body.email).lower(), phone=body.phone, emergency_contact=body.emergency_contact,
            date_joined=body.date_joined, supervisor_id=body.supervisor_id, weekly_schedule=body.weekly_schedule)
        emp.locations = [EmployeeLocation(location_id=i) for i in set(body.location_ids)]
        db.add(emp)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Employee code or email already exists") from None
    db.refresh(emp)
    audit(db, user, "employee.create", "employee", emp.id, None, _snapshot(emp))
    db.commit()
    return serialize(emp, True)


@router.get("/{employee_id}")
def get_employee(employee_id: int, user: User = Depends(require("employee.view")), db: Session = Depends(get_db)):
    emp = _get_visible(db, user, employee_id)
    return serialize(emp, user.role.name == "manager")


@router.put("/{employee_id}")
def update_employee(employee_id: int, body: EmployeeUpdate, user: User = Depends(require("employee.manage")),
                    db: Session = Depends(get_db)):
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    data = body.model_dump(exclude_unset=True)
    _validate_refs(db, data.get("location_ids") or _location_ids(emp), data.get("supervisor_id"))
    before = _snapshot(emp)
    if "location_ids" in data:
        wanted = set(data.pop("location_ids"))
        emp.locations = [el for el in emp.locations if el.location_id in wanted] + [
            EmployeeLocation(employee_id=emp.id, location_id=i) for i in wanted - set(_location_ids(emp))]
    if "role" in data:
        new_role = db.scalar(select(Role).where(Role.name == data.pop("role")))
        if emp.user:
            emp.user.role_id = new_role.id
    for key, value in data.items():
        setattr(emp, key, value)
    db.flush()
    db.refresh(emp)
    after = _snapshot(emp)
    audit(db, user, "employee.update", "employee", emp.id, before, after)
    if (before["location_ids"], before["supervisor_id"]) != (after["location_ids"], after["supervisor_id"]):
        audit(db, user, "employee.assignment_change", "employee", emp.id,
              {k: before[k] for k in ("location_ids", "supervisor_id")},
              {k: after[k] for k in ("location_ids", "supervisor_id")})
    db.commit()
    return serialize(emp, True)


def _set_active(db: Session, user: User, employee_id: int, active: bool) -> dict:
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    if emp.user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own account status")
    before = emp.status
    emp.status = "active" if active else "inactive"
    if emp.user:
        emp.user.active = active
    audit(db, user, "employee.activate" if active else "employee.deactivate", "employee", emp.id,
          {"status": before}, {"status": emp.status})
    db.commit()
    return serialize(emp, True)


@router.post("/{employee_id}/deactivate")
def deactivate(employee_id: int, user: User = Depends(require("employee.manage")), db: Session = Depends(get_db)):
    return _set_active(db, user, employee_id, False)


@router.post("/{employee_id}/activate")
def activate(employee_id: int, user: User = Depends(require("employee.manage")), db: Session = Depends(get_db)):
    return _set_active(db, user, employee_id, True)


@router.get("/{employee_id}/history")
def history(employee_id: int, user: User = Depends(require("attendance.view")), db: Session = Depends(get_db)):
    emp = _get_visible(db, user, employee_id)
    records = db.scalars(select(AttendanceRecord).where(AttendanceRecord.employee_id == emp.id)
                         .order_by(AttendanceRecord.check_in_at.desc()).limit(30))
    tasks = db.execute(
        select(ChecklistInstance.status).where(ChecklistInstance.completed_by == emp.user_id)).scalars().all()
    return {
        "attendance": [row(r, "id", "location_id", "local_date", "check_in_at", "check_out_at", "late_minutes",
                           "payable_minutes", "overtime_minutes") for r in records],
        "tasks_completed": len(tasks),
    }
