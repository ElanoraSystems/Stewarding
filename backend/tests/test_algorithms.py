"""The optimised paths must give exactly the answers of the obvious slow version."""
import random
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, select

from app.db import engine
from app.models import InventoryItem, Location, Setting, StockTransaction
from app.services.inventory import _month_bounds, reconcile
from app.services.monitoring import has_reading
from app.services.settings import DEFAULTS, get_setting
from app.services.similarity import classify, find_similar, within_edits

from .helpers import MGR, STEWARD
from .test_monitoring import mk_stage, record


def naive_reconcile(db, location, month):
    """The original method: for each item, scan every movement of the location."""
    start, end = _month_bounds(location.timezone, month)
    txns = db.scalars(select(StockTransaction).where(StockTransaction.location_id == location.id, StockTransaction.occurred_at < end)).all()
    out = {}
    for item in db.scalars(select(InventoryItem)):
        mine = [t for t in txns if t.item_id == item.id]
        if not mine:
            continue
        month_txns = [t for t in mine if t.occurred_at >= start]
        total = lambda *types: sum(t.qty_delta for t in month_txns if t.txn_type in types)  # noqa: E731
        before = sum(t.qty_delta for t in mine if t.occurred_at < start)
        parts = (total("opening"), total("receipt"), total("return"), total("issue"), total("breakage", "damage"),
                 total("transfer_in"), total("transfer_out"), total("adjustment"))
        out[item.code] = (before, *parts, before + sum(parts))
    return out


def test_reconcile_matches_the_brute_force_answer_on_random_ledgers(client, login, db, clock):
    rng = random.Random(11)
    mk = db.scalar(select(Location).where(Location.code == "MK"))
    items = [i for (i,) in db.execute(select(InventoryItem.id))]
    kinds = ["receipt", "issue", "return", "damage", "breakage", "adjustment", "transfer_in", "transfer_out", "opening"]
    for _ in range(600):
        db.add(StockTransaction(item_id=rng.choice(items), location_id=mk.id, txn_type=rng.choice(kinds), qty_delta=rng.randint(-9, 25),
                                user_id=1, occurred_at=datetime(2026, 3, 2) + timedelta(days=rng.randint(-70, 40), minutes=rng.randint(0, 1400))))
    db.commit()
    for month in ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05"):
        fast = {r["code"]: (r["opening"], r["opening_stock"], r["receipts"], r["returns"], r["issues"], r["breakage_damage"],
                            r["transfers_in"], r["transfers_out"], r["adjustments"], r["closing"]) for r in reconcile(db, mk, month)}
        assert fast == naive_reconcile(db, mk, month), month


@pytest.mark.parametrize("seed", range(5))
def test_binary_search_agrees_with_scanning_every_reading(seed):
    rng = random.Random(seed)
    base = datetime(2026, 3, 1)
    times = sorted(base + timedelta(minutes=rng.randint(0, 5000)) for _ in range(rng.randint(0, 60)))
    for _ in range(400):
        low = base + timedelta(minutes=rng.randint(-100, 5100))
        high = low + timedelta(minutes=rng.randint(0, 600))
        assert has_reading(times, low, high) == any(low <= t < high for t in times)
    assert has_reading([], base, base + timedelta(days=1)) is False


def test_the_window_is_half_open():
    t = datetime(2026, 3, 1, 12)
    assert has_reading([t], t, t + timedelta(minutes=1)) is True       # the start is included
    assert has_reading([t], t - timedelta(minutes=1), t) is False       # the end is not


@pytest.mark.parametrize("query,name,expected", [
    ("Dinner Plate 27cm", "dinner  plate 27 CM", "same"),
    ("Dinner Plate 27cm", "Plate, Dinner 27cm", "same"),
    ("Dinner Plates 27cm", "Dinner Plate 27cm", "same"),
    ("Dinner-Plate 27cm", "Dinner Plate 27cm", "same"),
    ("Dinner Plat 27cm", "Dinner Plate 27cm", "similar"),
    ("Dinner Plate", "Dinner Plate 27cm", "similar"),
    ("Soup Bowl", "Dinner Plate 27cm", None),
    ("Side Plate 18cm", "Dinner Plate 27cm", None),
    ("Glass", "Glasses", "similar"),
    ("", "Dinner Plate", None),
])
def test_names_are_classified(query, name, expected):
    assert classify(query, name) == expected


def test_edit_distance_limit():
    assert within_edits("plate", "plate", 0) and within_edits("plate", "plat", 1) and within_edits("plate", "plote", 1)
    assert not within_edits("plate", "bowl", 1) and not within_edits("plate", "plates and more", 2)
    assert within_edits("kitten", "sitting", 3) and not within_edits("kitten", "sitting", 2)


def test_similar_names_are_ranked_with_the_same_item_first():
    rows = [(1, "A", "Dinner Plate Large", True), (2, "B", "Dinner Plate 27cm", True), (3, "C", "Soup Bowl", True), (4, "D", "dinner plat 27cm", False)]
    found = find_similar("Dinner Plate 27cm", rows)
    assert [f["code"] for f in found][0] == "B" and found[0]["match"] == "same"
    assert "C" not in [f["code"] for f in found]
    assert len(find_similar("plate", rows, limit=1)) == 1


def test_a_reordered_or_respaced_name_is_refused_but_a_typo_only_warns(client, login, db):
    m = login(MGR)
    cat = client.get("/api/inventory/categories", headers=m).json()[0]["id"]
    unit = client.get("/api/inventory/units", headers=m).json()[0]["id"]

    def create(name):
        return client.post("/api/inventory/items", json={"name": name, "category_id": cat, "unit_id": unit}, headers=m)

    for same in ("27cm Dinner Plate", "Dinner-Plate 27 cm", "dinner plates 27cm"):
        r = create(same)
        assert r.status_code == 409 and "Dinner Plate 27cm (PL-001)" in r.json()["detail"], same
    found = client.get("/api/inventory/items/lookup?q=Dinner Plat 27cm", headers=m).json()
    assert found[0]["code"] == "PL-001" and found[0]["match"] == "similar"
    assert client.get("/api/inventory/items/lookup?q=27cm plate dinner", headers=m).json()[0]["match"] == "same"
    assert create("Dinner Plat 27cm").status_code == 201  # only the same item is blocked; the form warns about close ones


def count_queries(fn):
    seen = []
    listener = lambda *_: seen.append(1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(seen)


def test_settings_are_read_once_per_transaction_and_stay_correct(db):
    assert count_queries(lambda: [get_setting(db, "temp.retest_minutes") for _ in range(50)]) == 1
    assert get_setting(db, "temp.retest_minutes") == DEFAULTS["temp.retest_minutes"]
    db.add(Setting(key="temp.retest_minutes", value={"v": 99}))
    db.flush()
    assert get_setting(db, "temp.retest_minutes") == 99          # a change is seen as soon as it is flushed
    db.commit()
    assert get_setting(db, "temp.retest_minutes") == 99
    row = db.get(Setting, "temp.retest_minutes")
    row.value = {"v": 7}
    db.flush()
    assert get_setting(db, "temp.retest_minutes") == 7
    db.rollback()
    assert get_setting(db, "temp.retest_minutes") == 99          # a rolled back change is forgotten


def test_a_page_of_readings_costs_the_same_number_of_queries_however_many_rows(client, login, db, clock):
    steward = login(STEWARD)
    eq, wash = mk_stage(client, steward)
    mgr = login(MGR)
    url = "/api/monitoring/readings?size=25"
    record(client, steward, eq, wash, 60)
    few = count_queries(lambda: client.get(url, headers=mgr))
    for _ in range(14):
        record(client, steward, eq, wash, 40, corrective_action="Descaled the heater")  # failed readings, each with an action
    many = count_queries(lambda: client.get(url, headers=mgr))
    assert many == few
