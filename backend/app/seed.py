import secrets
from datetime import date, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import (Employee, EmployeeLocation, Equipment, EquipmentSchedule, InventoryCategory, InventoryItem,
                     InventoryUnit, Location, LookupValue, Role, RolePermission, Shift, ShiftAssignment, Supplier,
                     TrackedAsset, User)
from .permissions import MANAGER, ROLE_PERMISSIONS, STEWARD, SUPERVISOR
from .security import hash_password
from .services.inventory import norm, post_txn
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
    if not db.scalar(select(Shift).where(Shift.kind == "weekoff")):
        db.add(Shift(name="Week Off", kind="weekoff", start_time=time(0), end_time=time(0), grace_minutes=0))
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
            ("DW-MK-1", "Main Kitchen Dishwasher 1", "Dishwasher", "MK", "sup.mk@example.test"),
            ("GW-MK-1", "Main Kitchen Glasswasher 1", "Glasswasher", "MK", "sup.mk@example.test"),
            ("DW-BQ-1", "Banquet Dishwasher 1", "Dishwasher", "BQ", "sup.mk@example.test"),
            ("GW-RB-1", "Rooftop Bar Glasswasher 1", "Glasswasher", "RB", "sup.rb@example.test"),
        ]:
            eq = Equipment(code=code, name=name, kind=kind, location_id=locs[loc_code].id,
                           supervisor_id=emps[sup].id, maintenance_notes=PLACEHOLDER_NOTE)
            db.add(eq)
            db.flush()
            db.add(EquipmentSchedule(equipment_id=eq.id, stage="wash", unit="°C", timing="startup", time_of_day=time(6),
                                     min_value=Decimal("55.0"), max_value=Decimal("65.0")))
            db.add(EquipmentSchedule(equipment_id=eq.id, stage="final_rinse", unit="°C", timing="startup", time_of_day=time(6),
                                     min_value=Decimal("80.0"), max_value=Decimal("90.0")))
    seed_inventory(db, db.scalar(select(User).where(User.email == PEOPLE[0][0])), locs)
    ensure_lookups(db)
    db.commit()


# code, name, category, unit, min, target, cost, tracked, opening stock by location code
ITEMS = [
    ("PL-001", "Dinner Plate 27cm", "Plates", "Each", 60, 300, "2.50", False, {"MK": 200, "BQ": 150, "RB": 40}),
    ("PL-002", "Side Plate 18cm", "Plates", "Each", 40, 200, "1.60", False, {"MK": 120, "BQ": 100}),
    ("BW-001", "Soup Bowl", "Bowls", "Each", 40, 150, "2.10", False, {"MK": 90, "BQ": 80}),
    ("CP-001", "Coffee Cup", "Cups & Saucers", "Each", 30, 120, "1.40", False, {"MK": 70, "BQ": 60, "RB": 50}),
    ("PT-001", "Serving Platter 40cm", "Platters", "Each", 6, 24, "14.00", False, {"BQ": 20, "MK": 10}),
    ("KN-001", "Chef Knife 20cm", "Knives", "Each", 3, 10, "22.00", True, {"MK": 8, "BQ": 4}),
    ("UT-001", "Ladle", "Utensils", "Each", 5, 15, "4.50", False, {"MK": 12, "BQ": 8, "RB": 3}),
    ("UT-002", "Tongs", "Utensils", "Each", 8, 25, "3.20", False, {"MK": 20, "BQ": 15, "RB": 6}),
    ("PN-001", "Stock Pot 20L", "Pots & Pans", "Each", 2, 8, "48.00", False, {"MK": 6, "BQ": 3}),
    ("TR-001", "Gastronorm Pan 1/1", "Trays & Containers", "Each", 10, 40, "18.00", False, {"MK": 30, "BQ": 24}),
]
CATEGORIES = ["Plates", "Bowls", "Cups & Saucers", "Platters", "Knives", "Utensils", "Pots & Pans", "Trays & Containers"]
CROCKERY_CATEGORIES = {"Plates", "Bowls", "Cups & Saucers", "Platters"}


LOOKUPS = {
    "job_title": ["Steward", "Senior Steward", "Stewarding Supervisor", "Back of House Manager"],
    "checklist_category": ["Cleaning", "Safety", "Equipment", "Storage", "Waste"],
    "breakage_reason": ["Dropped while carrying", "Slipped while stacking", "Chipped in dishwasher", "Thermal shock",
                        "Defective item", "Cause unknown"],
    "corrective_action": ["Re-ran the wash cycle", "Cleaned spray arms and filters", "Descaled the machine",
                          "Refilled chemical", "Called the engineer"],
    "monitoring_type": ["Cold storage", "Defrosting", "Cooking", "Reheating", "Cooling", "Hot holding", "Sanitising", "Dishwasher",
                        "Glasswasher", "Traceability", "Calibration", "Other"],
}
SUPPLIERS = ["Gulf Catering Supplies", "Hotel Ware Trading"]


def ensure_lookups(db: Session) -> None:
    """Default dropdown values; safe to run repeatedly."""
    for kind, values in LOOKUPS.items():
        for value in values:
            if not db.scalar(select(LookupValue.id).where(LookupValue.kind == kind, LookupValue.value_key == norm(value))):
                db.add(LookupValue(kind=kind, value=value, value_key=norm(value)))
    db.flush()


def seed_inventory(db: Session, manager: User, locs: dict[str, Location]) -> None:
    if db.scalar(select(InventoryItem.id).limit(1)):
        return
    units = {name: InventoryUnit(name=name) for name in ("Each", "Dozen", "Set")}
    db.add_all(units.values())
    cats = {name: InventoryCategory(name=name) for name in CATEGORIES}
    db.add_all(cats.values())
    suppliers = {name: Supplier(name=name, name_key=norm(name)) for name in SUPPLIERS}
    db.add_all(suppliers.values())
    db.flush()
    for code, name, cat, unit, low, target, cost, tracked, opening in ITEMS:
        item = InventoryItem(code=code, name=name, name_key=norm(name), category_id=cats[cat].id,
                             unit_id=units[unit].id, min_level=low, target_level=target, unit_cost=Decimal(cost),
                             is_tracked_asset=tracked, opening_qty=sum(opening.values()), storage_location="Dry store",
                             supplier_id=suppliers[SUPPLIERS[0 if cat in CROCKERY_CATEGORIES else 1]].id)
        db.add(item)
        db.flush()
        for loc_code, qty in opening.items():
            post_txn(db, manager, item, locs[loc_code].id, "opening", qty, "Opening stock")
        if tracked:
            for loc_code, qty in opening.items():
                for n in range(1, min(qty, 3) + 1):
                    db.add(TrackedAsset(item_id=item.id, asset_tag=f"{code}-{loc_code}-{n:02d}", location_id=locs[loc_code].id))


def main() -> None:
    password = settings.seed_password or secrets.token_urlsafe(12)
    with SessionLocal() as db:
        seed(db, password)
    if not settings.seed_password:
        print(f"Seeded users with generated password: {password}")
    print("Seed complete: " + ", ".join(p[0] for p in PEOPLE))


if __name__ == "__main__":
    main()
