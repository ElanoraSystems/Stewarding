"""Times the main screens and reports on two years of data: `python -m scripts.benchmark_scale [--years N]`.

It builds a throwaway database for a busy three-location kitchen (60 employees, 14 monitoring points, hundreds of stock items),
then times each endpoint and counts its queries. Set STW_BENCH_DATABASE_URL to a disposable PostgreSQL database to time PostgreSQL.
"""
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta

_tmp = tempfile.mkdtemp()
os.environ["STW_DATABASE_URL"] = os.environ.get("STW_BENCH_DATABASE_URL", f"sqlite:///{_tmp}/scale.db")
os.environ["STW_SECRET_KEY"] = "benchmark-only-secret-key-not-for-production"
os.environ["STW_SCHEDULER_ENABLED"] = "false"
os.environ["STW_BCRYPT_ROUNDS"] = "4"
os.environ["STW_UPLOAD_DIR"] = f"{_tmp}/uploads"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, func, select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (AttendanceRecord, AuditLog, ChecklistInstance, ChecklistTask, ChecklistTemplate, Employee, EmployeeLocation,  # noqa: E402
                        Equipment, EquipmentSchedule, InventoryBalance, InventoryItem, Location, Notification, Shift,
                        ShiftAssignment, StockTransaction, TemperatureReading, User)
from app.security import hash_password  # noqa: E402
from app.seed import seed  # noqa: E402

PASSWORD = "bench-pass-12345"
YEARS = int(sys.argv[sys.argv.index("--years") + 1]) if "--years" in sys.argv else 2
DAYS = 365 * YEARS
STAFF = 60
ITEMS = 400
TXNS = 150_000
POINTS = 14


class Counter:
    def __init__(self):
        self.count = 0
        event.listen(engine, "before_cursor_execute", self._hit)

    def _hit(self, *_):
        self.count += 1


def chunked(db, model, rows, size=5000):
    for i in range(0, len(rows), size):
        db.bulk_insert_mappings(model, rows[i:i + size])
        db.commit()


def build(db) -> dict:
    seed(db, PASSWORD)
    rng = random.Random(11)
    now = datetime.utcnow()
    today = now.date()
    locs = [loc.id for loc in db.scalars(select(Location))]
    shift = db.scalar(select(Shift).where(Shift.kind == "work"))
    hashed = hash_password(PASSWORD)
    for n in range(STAFF - 6):
        user = User(email=f"staff{n}@example.com", password_hash=hashed, role_id=3)
        db.add(user)
        db.flush()
        emp = Employee(employee_code=f"S{n:03d}", user_id=user.id, full_name=f"Staff Member {n}", job_title="Steward", email=user.email)
        emp.locations = [EmployeeLocation(location_id=locs[n % len(locs)])]
        db.add(emp)
        db.flush()
        for weekday in range(7):
            db.add(ShiftAssignment(employee_id=emp.id, shift_id=shift.id, location_id=locs[n % len(locs)], weekday=weekday,
                                   valid_from=today - timedelta(days=DAYS + 30)))
    db.commit()
    people = [(e.id, e.locations[0].location_id) for e in db.scalars(select(Employee))]

    rows = []
    for emp_id, loc in people:
        for d in range(1, DAYS):
            day = today - timedelta(days=d)
            start = datetime.combine(day, datetime.min.time()) + timedelta(hours=2, minutes=rng.randint(0, 20))
            rows.append({"employee_id": emp_id, "location_id": loc, "shift_id": shift.id, "local_date": day, "check_in_at": start,
                         "check_out_at": start + timedelta(hours=8), "late_minutes": rng.choice([0, 0, 0, 5, 20]),
                         "payable_minutes": 450, "overtime_minutes": 0})
    chunked(db, AttendanceRecord, rows)

    rows = []
    for task, template in db.execute(select(ChecklistTask, ChecklistTemplate).join(ChecklistTemplate, ChecklistTemplate.id == ChecklistTask.template_id)):
        for d in range(0, DAYS):
            day = today - timedelta(days=d)
            rows.append({"task_id": task.id, "location_id": template.location_id, "local_date": day, "shift_key": 0,
                         "status": rng.choice(["verified", "completed", "completed", "overdue"]),
                         "due_at": datetime.combine(day, datetime.min.time()) + timedelta(hours=9), "completed_by": 1,
                         "completed_at": datetime.combine(day, datetime.min.time()) + timedelta(hours=8)})
    chunked(db, ChecklistInstance, rows)

    for n in range(POINTS):
        eq = Equipment(code=f"SC-{n}", name=f"Scale point {n}", kind="Cold storage", location_id=locs[n % len(locs)])
        db.add(eq)
        db.flush()
        for hour in (8, 12, 16):
            db.add(EquipmentSchedule(equipment_id=eq.id, stage=f"Check {hour}", parameter="Temperature", unit="C", value_type="number",
                                     timing="checkpoint", time_of_day=datetime.min.time().replace(hour=hour), min_value=0, max_value=5))
    db.commit()
    rows = []
    for sched in db.scalars(select(EquipmentSchedule).where(EquipmentSchedule.stage.like("Check %"))):
        eq = db.get(Equipment, sched.equipment_id)
        for d in range(0, DAYS):
            at = datetime.combine(today - timedelta(days=d), datetime.min.time()) + timedelta(hours=sched.time_of_day.hour - 4, minutes=rng.randint(0, 20))
            if at <= now and rng.random() < 0.95:
                value = rng.choice([3, 3, 3, 4, 7])
                reviewed = rng.random() < 0.9
                rows.append({"equipment_id": eq.id, "schedule_id": sched.id, "location_id": eq.location_id, "recorded_at": at, "stage": sched.stage,
                             "source": "machine_display", "parameter": "Temperature", "unit": "C", "value_type": "number", "value": value,
                             "min_limit": 0, "max_limit": 5, "passed": value <= 5, "recorded_by": 1,
                             "reviewed_by": 2 if reviewed else None, "reviewed_at": at + timedelta(hours=2) if reviewed else None})
    chunked(db, TemperatureReading, rows)

    db.bulk_insert_mappings(InventoryItem, [{"code": f"B-{n:05d}", "name": f"Bench Item {n}", "name_key": f"bench item {n}", "compact_key": f"benchitem{n}",
                                             "token_key": f"{n} bench item", "category_id": 1, "unit_id": 1, "min_level": 5, "active": True} for n in range(ITEMS)])
    db.commit()
    item_ids = [i for (i,) in db.execute(select(InventoryItem.id).where(InventoryItem.code.like("B-%")))]
    rows, balances = [], {}
    for _ in range(TXNS):
        item, loc = rng.choice(item_ids), rng.choice(locs)
        kind, delta = rng.choice([("receipt", rng.randint(5, 40)), ("issue", -rng.randint(1, 15)), ("breakage", -1)])
        balances[(item, loc)] = balances.get((item, loc), 0) + delta
        rows.append({"item_id": item, "location_id": loc, "txn_type": kind, "qty_delta": delta, "user_id": 1,
                     "occurred_at": now - timedelta(days=rng.randint(0, DAYS), minutes=rng.randint(0, 1000))})
    chunked(db, StockTransaction, rows)
    db.bulk_insert_mappings(InventoryBalance, [{"item_id": i, "location_id": loc, "qty": max(q, 0)} for (i, loc), q in balances.items()])
    db.commit()

    chunked(db, AuditLog, [{"created_at": now - timedelta(minutes=rng.randint(0, DAYS * 1440)), "user_id": rng.choice([1, 2, 3]),
                            "action": rng.choice(["attendance.manual", "employee.update", "equipment.update"]), "entity": "x", "entity_id": n}
                           for n in range(150_000)])
    chunked(db, Notification, [{"user_id": rng.choice([1, 2, 3]), "kind": "low_stock", "priority": "normal", "title": f"Low stock {n}",
                                "dedupe_key": f"bench:{n}", "created_at": now - timedelta(minutes=rng.randint(0, DAYS * 1440))} for n in range(60_000)])
    counts = {name: db.scalar(select(func.count()).select_from(model)) for name, model in
              (("attendance", AttendanceRecord), ("checklist instances", ChecklistInstance), ("readings", TemperatureReading),
               ("stock movements", StockTransaction), ("audit rows", AuditLog), ("notifications", Notification))}
    print("dataset: " + ", ".join(f"{v:,} {k}" for k, v in counts.items()))
    return {"today": today}


def main() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    began = time.perf_counter()
    with SessionLocal() as db:
        today = build(db)["today"]
    print(f"built in {time.perf_counter() - began:.0f}s")
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"email": "manager@example.test", "password": PASSWORD}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    iso = lambda d: d.isoformat()  # noqa: E731
    two_years = f"date_from={iso(today - timedelta(days=DAYS))}&date_to={iso(today)}"
    one_year = f"date_from={iso(today - timedelta(days=364))}&date_to={iso(today)}"
    month = f"date_from={iso(today - timedelta(days=30))}&date_to={iso(today + timedelta(days=1))}"
    last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    paths = [
        ("dashboard, default", "/api/dashboard"),
        ("dashboard, 90 days", f"/api/dashboard?date_from={iso(today - timedelta(days=89))}&date_to={iso(today)}"),
        ("monitoring log page 1", "/api/monitoring/readings?size=25"),
        ("monitoring log page 600", "/api/monitoring/readings?size=25&page=600"),
        ("monitoring log, whole period", f"/api/monitoring/readings?size=25&{two_years}"),
        ("monitoring due today", "/api/monitoring/due?location_id=1"),
        ("attendance page 1", "/api/attendance?size=15"),
        ("attendance one employee, whole period", f"/api/attendance?size=15&employee_id=10&{two_years}"),
        ("checklist day", f"/api/checklists/instances?day={iso(today)}&size=200"),
        ("employees page", "/api/employees?size=15"),
        ("notifications", "/api/notifications?size=15"),
        ("audit log", "/api/audit?size=25"),
        ("stock transactions page 1", "/api/inventory/transactions?size=25"),
        ("stock transactions page 3000", "/api/inventory/transactions?size=25&page=3000"),
        ("reconciliation, last month", f"/api/stock/reconciliation?location_id=1&month={last_month}"),
        ("stock insights, one year", f"/api/stock/insights?{one_year}"),
        ("pending summary", "/api/notifications/pending-summary"),
        ("daily report", "/api/reports/daily"),
        ("weekly report", "/api/reports/weekly"),
        ("monthly report", "/api/reports/monthly"),
        ("monitoring record, month", f"/api/reports/records/monitoring?{month}"),
        ("attendance record, month", f"/api/reports/records/attendance?{month}"),
        ("attendance sheet, month", f"/api/reports/records/attendance_sheet?{month}"),
        ("movements record, month", f"/api/reports/records/movements?{month}"),
        ("attendance record, one year", f"/api/reports/records/attendance?{one_year}"),
        ("monitoring record, one year", f"/api/reports/records/monitoring?{one_year}"),
        ("checklist record, one year", f"/api/reports/records/checklists?{one_year}"),
        ("movements record, two years", f"/api/reports/records/movements?{two_years}"),
        ("attendance record Excel, one year", f"/api/reports/records/attendance/export?fmt=xlsx&{one_year}"),
        ("attendance record PDF, one year", f"/api/reports/records/attendance/export?fmt=pdf&{one_year}"),
        ("monitoring record PDF, month", f"/api/reports/records/monitoring/export?fmt=pdf&{month}"),
        ("attendance sheet PDF, month", f"/api/reports/records/attendance_sheet/export?fmt=pdf&{month}"),
    ]
    width = max(len(p[0]) for p in paths)
    print(f"\n{'path'.ljust(width)}  {'ms':>8}  {'queries':>8}  status")
    for label, path in paths:
        counter = Counter()
        started = time.perf_counter()
        response = client.get(path, headers=auth)
        ms = (time.perf_counter() - started) * 1000
        event.remove(engine, "before_cursor_execute", counter._hit)
        print(f"{label.ljust(width)}  {ms:8.0f}  {counter.count:8d}  {response.status_code}{'  SLOW' if ms > 500 else ''}")


if __name__ == "__main__":
    main()
