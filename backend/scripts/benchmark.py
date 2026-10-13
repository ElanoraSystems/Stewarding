"""Times the heavy read paths on a large synthetic dataset: `python -m scripts.benchmark [--small]`.

It builds a throwaway SQLite database, so nothing real is touched. Set STW_BENCH_DATABASE_URL to a disposable PostgreSQL
database to time PostgreSQL instead; the tables are dropped and recreated there. Run it before and after a change to see the effect.
"""
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta

_tmp = tempfile.mkdtemp()
os.environ["STW_DATABASE_URL"] = os.environ.get("STW_BENCH_DATABASE_URL", f"sqlite:///{_tmp}/bench.db")
os.environ["STW_SECRET_KEY"] = "benchmark-only-secret-key-not-for-production"
os.environ["STW_SCHEDULER_ENABLED"] = "false"
os.environ["STW_BCRYPT_ROUNDS"] = "4"
os.environ["STW_UPLOAD_DIR"] = f"{_tmp}/uploads"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, select  # noqa: E402

from app import timeutil  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (Equipment, EquipmentSchedule, InventoryBalance, InventoryItem, Location, StockTransaction,  # noqa: E402
                        TemperatureReading)
from app.seed import seed  # noqa: E402
from app.services import metrics  # noqa: E402
from app.services.inventory import reconcile  # noqa: E402
from app.services.monitoring import due_checks  # noqa: E402
from app.services import snapshots  # noqa: E402

PASSWORD = "bench-pass-12345"
SMALL = "--small" in sys.argv
ITEMS = 60 if SMALL else 400
TXNS_PER_ITEM = 40 if SMALL else 230
POINTS = 4 if SMALL else 14
DAYS = 14 if SMALL else 45


class QueryCounter:
    def __init__(self):
        self.count = 0
        event.listen(engine, "before_cursor_execute", self._hit)

    def _hit(self, *_):
        self.count += 1


def build(db) -> None:
    seed(db, PASSWORD)
    rng = random.Random(7)
    now = datetime.utcnow()
    db.bulk_insert_mappings(InventoryItem, [{"code": f"B-{n:05d}", "name": f"Bench Item {n}", "name_key": f"bench item {n}", "compact_key": f"benchitem{n}", "token_key": f"{n} bench item",
                                             "category_id": 1, "unit_id": 1, "min_level": 5, "active": True} for n in range(ITEMS)])
    db.commit()
    item_ids = [i for (i,) in db.execute(select(InventoryItem.id).where(InventoryItem.code.like("B-%")))]
    loc_ids = [i for (i,) in db.execute(select(Location.id))]
    rows, balances = [], {}
    for item_id in item_ids:
        for loc_id in loc_ids:
            level = 0
            for _ in range(TXNS_PER_ITEM // len(loc_ids)):
                kind, delta = rng.choice([("receipt", rng.randint(5, 40)), ("issue", -rng.randint(1, 15)), ("breakage", -1)])
                if level + delta < 0:
                    kind, delta = "receipt", 20
                level += delta
                rows.append({"item_id": item_id, "location_id": loc_id, "txn_type": kind, "qty_delta": delta, "user_id": 1,
                             "occurred_at": now - timedelta(days=rng.randint(0, DAYS * 2), minutes=rng.randint(0, 1000))})
            balances[(item_id, loc_id)] = level
    db.bulk_insert_mappings(StockTransaction, rows)
    db.bulk_insert_mappings(InventoryBalance, [{"item_id": i, "location_id": loc, "qty": q} for (i, loc), q in balances.items()])
    db.commit()

    mk = db.scalar(select(Location).where(Location.code == "MK"))
    for n in range(POINTS):
        eq = Equipment(code=f"BP-{n}", name=f"Bench point {n}", kind="Cold storage", location_id=mk.id)
        db.add(eq)
        db.flush()
        for stage in ("morning", "evening"):
            db.add(EquipmentSchedule(equipment_id=eq.id, stage=stage, parameter="Temperature", unit="C", value_type="number",
                                     timing="interval", interval_minutes=60, min_value=0, max_value=5))
    db.commit()
    readings = []
    for sched in db.scalars(select(EquipmentSchedule)):
        eq = db.get(Equipment, sched.equipment_id)
        tz = db.get(Location, eq.location_id).timezone
        for day_back in range(DAYS):
            day = timeutil.local_date(now, tz) - timedelta(days=day_back)
            for hour in range(24):
                when = timeutil.local_to_utc(day, datetime.min.time().replace(hour=hour), tz)
                if when <= now and rng.random() < 0.9:
                    readings.append({"equipment_id": eq.id, "schedule_id": sched.id, "location_id": eq.location_id,
                                     "recorded_at": when + timedelta(minutes=rng.randint(0, 20)), "stage": sched.stage,
                                     "source": "machine_display", "parameter": "Temperature", "unit": "C", "value_type": "number",
                                     "value": 3, "min_limit": 0, "max_limit": 5, "passed": True, "recorded_by": 1})
    db.bulk_insert_mappings(TemperatureReading, readings)
    db.commit()
    print(f"dataset: {ITEMS} items, {len(rows):,} stock movements, {len(readings):,} readings, {POINTS} monitoring points, {DAYS} days")


def timed(label: str, fn, repeat: int = 3) -> tuple[str, float, int]:
    counter = QueryCounter()
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    event.remove(engine, "before_cursor_execute", counter._hit)
    return label, best * 1000, counter.count // repeat


def main() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        build(db)
        now = datetime.utcnow()
        mk = db.scalar(select(Location).where(Location.code == "MK"))
        month = now.strftime("%Y-%m")
        points = list(db.scalars(select(Equipment).where(Equipment.location_id == mk.id)))
        today = timeutil.local_date(now, mk.timezone)
        wins = metrics.windows(db, now, None, mk.id, today - timedelta(days=DAYS - 1), today)
        client = TestClient(app)
        token = client.post("/api/auth/login", json={"email": "manager@example.test", "password": PASSWORD}).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        results = [
            timed("reconcile: one location, one month", lambda: reconcile(db, mk, month)),
            timed("reconcile with month-end snapshots", lambda: (snapshots.refresh(db, now), db.commit(), reconcile(db, mk, month))[-1], repeat=1),
            timed("reconcile again, snapshots in place", lambda: reconcile(db, mk, month)),
            timed("due_checks: today, all points", lambda: due_checks(db, points, now)),
            timed("monitoring_stats: whole range", lambda: metrics.monitoring_stats(db, wins[0], now)),
            timed("GET /api/dashboard", lambda: client.get("/api/dashboard", headers=auth)),
            timed("GET /api/monitoring/readings (25)", lambda: client.get("/api/monitoring/readings?size=25", headers=auth)),
            timed("GET /api/inventory/items (25)", lambda: client.get("/api/inventory/items?size=25", headers=auth)),
            timed("GET /api/stock/reconciliation", lambda: client.get(f"/api/stock/reconciliation?location_id={mk.id}&month={month}", headers=auth)),
        ]
    width = max(len(r[0]) for r in results)
    print(f"\n{'path'.ljust(width)}  {'best ms':>9}  {'queries':>8}")
    for label, ms, queries in results:
        print(f"{label.ljust(width)}  {ms:9.1f}  {queries:8d}")


if __name__ == "__main__":
    main()
