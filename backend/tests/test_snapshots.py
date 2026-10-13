import random
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import InventoryItem, Location, Notification, StockSnapshot, StockTransaction
from app.scheduler import run_cycle
from app.services import snapshots
from app.services.inventory import reconcile

from .helpers import MGR
from .test_algorithms import naive_reconcile

MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")


def ledger(db, mk, seed=2, rows=500):
    rng = random.Random(seed)
    items = [i for (i,) in db.execute(select(InventoryItem.id))]
    kinds = ["receipt", "issue", "return", "damage", "breakage", "adjustment", "transfer_in", "transfer_out"]
    for _ in range(rows):
        db.add(StockTransaction(item_id=rng.choice(items), location_id=mk.id, txn_type=rng.choice(kinds), qty_delta=rng.randint(-9, 25),
                                user_id=1, occurred_at=datetime(2026, 1, 20) + timedelta(days=rng.randint(0, 120), minutes=rng.randint(0, 1400))))
    db.commit()


def fast(db, mk, month):
    return {r["code"]: (r["opening"], r["opening_stock"], r["receipts"], r["returns"], r["issues"], r["breakage_damage"],
                        r["transfers_in"], r["transfers_out"], r["adjustments"], r["closing"]) for r in reconcile(db, mk, month)}


def test_reconciliation_is_the_same_with_and_without_snapshots(client, login, db, clock):
    mk = db.scalar(select(Location).where(Location.code == "MK"))
    ledger(db, mk)
    clock.set(2026, 5, 15, 8, 0)
    without = {m: fast(db, mk, m) for m in MONTHS}
    assert without == {m: naive_reconcile(db, mk, m) for m in MONTHS}
    result = snapshots.refresh(db, clock.now)
    db.commit()
    assert result["built"] >= 4 and result["healed"] == 0
    assert {m: fast(db, mk, m) for m in MONTHS} == without


def test_a_snapshot_is_really_used_and_a_wrong_one_is_caught_and_healed(client, login, db, clock):
    mk = db.scalar(select(Location).where(Location.code == "MK"))
    ledger(db, mk)
    clock.set(2026, 5, 15, 8, 0)
    snapshots.refresh(db, clock.now)
    db.commit()
    truth = fast(db, mk, "2026-05")
    row = db.scalar(select(StockSnapshot).where(StockSnapshot.location_id == mk.id, StockSnapshot.month == "2026-04").limit(1))
    code = db.get(InventoryItem, row.item_id).code
    row.qty += 1000  # a damaged copy
    db.commit()
    assert fast(db, mk, "2026-05")[code][0] == truth[code][0] + 1000          # proves reconciliation starts from the snapshot
    again = snapshots.refresh(db, clock.now)
    db.commit()
    assert again["healed"] == 1
    assert db.scalar(select(Notification).where(Notification.kind == "snapshot_mismatch"))
    assert fast(db, mk, "2026-05") == truth                                    # back to the full ledger sum at once
    rebuilt = snapshots.refresh(db, clock.now)
    db.commit()
    assert rebuilt["built"] >= 1 and rebuilt["healed"] == 0
    assert fast(db, mk, "2026-05") == truth and snapshots.differences(db, mk, "2026-04") == []


def test_incremental_builds_equal_the_full_sum_and_the_job_is_idempotent(client, login, db, clock):
    mk = db.scalar(select(Location).where(Location.code == "MK"))
    ledger(db, mk, seed=9)
    clock.set(2026, 5, 15, 8, 0)
    first = snapshots.refresh(db, clock.now)
    db.commit()
    assert all(snapshots.differences(db, mk, m) == [] for m in snapshots.closed_months(db, mk, clock.now))
    assert "2026-05" not in snapshots.closed_months(db, mk, clock.now)       # the current month has not ended
    second = snapshots.refresh(db, clock.now)
    assert first["built"] > 0 and second == {"built": 0, "healed": 0}


def test_changing_a_location_time_zone_drops_its_snapshots(client, login, db, clock):
    mk = db.scalar(select(Location).where(Location.code == "MK"))
    ledger(db, mk, rows=120)
    clock.set(2026, 5, 15, 8, 0)
    snapshots.refresh(db, clock.now)
    db.commit()
    assert db.scalar(select(StockSnapshot.id).where(StockSnapshot.location_id == mk.id))
    r = client.put(f"/api/settings/locations/{mk.id}", json={"timezone": "Asia/Kuwait"}, headers=login(MGR))
    assert r.status_code == 200
    db.expire_all()
    assert db.scalar(select(StockSnapshot.id).where(StockSnapshot.location_id == mk.id)) is None


def test_the_scheduler_builds_snapshots(client, login, db, clock):
    mk = db.scalar(select(Location).where(Location.code == "MK"))
    ledger(db, mk, rows=120)
    clock.set(2026, 5, 15, 8, 0)
    out = run_cycle(db, clock.now)
    assert out["snapshots"]["built"] >= 3 and out["snapshots"]["healed"] == 0
    assert db.scalar(select(StockSnapshot.id).where(StockSnapshot.month == "2026-04"))
