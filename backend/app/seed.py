import secrets
from datetime import date, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import (Employee, EmployeeLocation, Equipment, EquipmentSchedule, Location, Role, RolePermission,
                     Shift, ShiftAssignment, User)
from .permissions import MANAGER, ROLE_PERMISSIONS, STEWARD, SUPERVISOR
from .security import hash_password
from .services.starter import apply_starter

LOCATIONS = [
    ("MK", "Main Kitchen", "kitchen", "Asia/Dubai"),
    ("BQ", "Banquet Hall", "banquet", "Asia/Dubai"),
    ("RB", "Rooftop Bar", "bar", "Europe/London"),
]
SHIFTS = [("Morning", time(6), time(14)), ("Evening", time(14), time(22))]
# email, code, name, title, role, location codes, supervisor email
PEOPLE = [
    ("manager@example.test", "E001", "Maya Manager", "Back of House Manager", MANAGER, ["MK", "BQ", "RB"], None),
    ("sup.mk@example.test", "E002", "Sam Supervisor", "Stewarding Supervisor", SUPERVISOR, ["MK", "BQ"], "manager@example.test"),
    ("sup.rb@example.test", "E003", "Rita Supervisor", "Stewarding Supervisor", SUPERVISOR, ["RB"], "manager@example.test"),
    ("steward.mk@example.test", "E004", "Sid Steward", "Steward", STEWARD, ["MK"], "sup.mk@example.test"),
    ("steward.bq@example.test", "E005", "Bina Steward", "Steward", STEWARD, ["BQ"], "sup.mk@example.test"),
    ("steward.rb@example.test", "E006", "Ravi Steward", "Steward", STEWARD, ["RB"], "sup.rb@example.test"),
]
PLACEHOLDER_NOTE = "PLACEHOLDER limits - set from the manufacturer's instructions and the approved food-safety procedure."


def sync_roles(db: Session) -> dict[str, Role]:
    roles = {}
    for name, perms in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.name == name)) or Role(name=name)
        role.permissions = [RolePermission(permission=p) for p in perms]
        db.add(role)
        roles[name] = role
    db.flush()
    return roles


def seed(db: Session, password: str) -> None:
    roles = sync_roles(db)
    locs = {}
    for code, name, kind, tz in LOCATIONS:
        loc = db.scalar(select(Location).where(Location.code == code)) or Location(code=code, name=name, kind=kind, timezone=tz)
        db.add(loc)
        locs[code] = loc
    shifts = {}
    for name, start, end in SHIFTS:
        shift = db.scalar(select(Shift).where(Shift.name == name)) or Shift(name=name, start_time=start, end_time=end)
        db.add(shift)
        shifts[name] = shift
    db.flush()

    emps: dict[str, Employee] = {}
    for email, code, name, title, role, loc_codes, sup in PEOPLE:
        if db.scalar(select(User).where(User.email == email)):
            emps[email] = db.scalar(select(Employee).where(Employee.employee_code == code))
            continue
        user = User(email=email, password_hash=hash_password(password), role_id=roles[role].id)
        db.add(user)
        db.flush()
        emp = Employee(employee_code=code, user_id=user.id, full_name=name, job_title=title, email=email,
                       date_joined=date(2025, 1, 6), supervisor_id=emps[sup].id if sup else None)
        emp.locations = [EmployeeLocation(location_id=locs[c].id) for c in loc_codes]
        db.add(emp)
        db.flush()
        emps[email] = emp
        if role == STEWARD:
            for weekday in range(7):
                db.add(ShiftAssignment(employee_id=emp.id, shift_id=shifts["Morning"].id,
                                       location_id=locs[loc_codes[0]].id, weekday=weekday, valid_from=date(2025, 1, 6)))

    for loc in locs.values():
        apply_starter(db, loc.id)

    if not db.scalar(select(Equipment.id).limit(1)):
        for code, name, kind, loc_code, sup in [
            ("DW-MK-1", "Main Kitchen Dishwasher 1", "dishwasher", "MK", "sup.mk@example.test"),
            ("GW-MK-1", "Main Kitchen Glasswasher 1", "glasswasher", "MK", "sup.mk@example.test"),
            ("DW-BQ-1", "Banquet Dishwasher 1", "dishwasher", "BQ", "sup.mk@example.test"),
            ("GW-RB-1", "Rooftop Bar Glasswasher 1", "glasswasher", "RB", "sup.rb@example.test"),
        ]:
            eq = Equipment(code=code, name=name, kind=kind, location_id=locs[loc_code].id,
                           supervisor_id=emps[sup].id, maintenance_notes=PLACEHOLDER_NOTE)
            db.add(eq)
            db.flush()
            db.add(EquipmentSchedule(equipment_id=eq.id, stage="wash", timing="startup", time_of_day=time(6),
                                     min_temp_c=Decimal("55.0"), max_temp_c=Decimal("65.0")))
            db.add(EquipmentSchedule(equipment_id=eq.id, stage="final_rinse", timing="interval", interval_minutes=240,
                                     min_temp_c=Decimal("80.0"), max_temp_c=Decimal("90.0")))
    db.commit()


def main() -> None:
    password = settings.seed_password or secrets.token_urlsafe(12)
    with SessionLocal() as db:
        seed(db, password)
    if not settings.seed_password:
        print(f"Seeded users with generated password: {password}")
    print("Seed complete: " + ", ".join(p[0] for p in PEOPLE))


if __name__ == "__main__":
    main()
