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
    ("Glass", "Glasses", "same"),
    ("Wine Glasses", "wine glass", "same"),
    ("Cutting Boxes", "Cutting Box", "same"),
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


def test_the_day_finder_agrees_with_converting_every_time_even_across_a_clock_change():
    from datetime import date

    from app import timeutil
    from app.services.metrics import Win, day_finder

    class Place:
        timezone = "Europe/London"

    first, last = date(2026, 3, 26), date(2026, 4, 1)  # the clocks go forward on 29 March
    win = Win(Place, first, last, timeutil.local_to_utc(first, datetime.min.time(), "Europe/London"),
              timeutil.local_to_utc(date(2026, 4, 2), datetime.min.time(), "Europe/London"), last)
    find = day_finder(win)
    rng = random.Random(3)
    moments = [win.start + timedelta(minutes=rng.randint(0, int((win.end - win.start).total_seconds() // 60) - 1)) for _ in range(3000)]
    moments += [win.start, win.end - timedelta(minutes=1), datetime(2026, 3, 29, 0, 59), datetime(2026, 3, 29, 1, 0), datetime(2026, 3, 28, 23, 59)]
    assert all(find(m) == timeutil.local_date(m, "Europe/London") for m in moments)


def test_movements_carry_the_same_days_as_the_per_row_conversion(client, login, db, clock):
    from app import timeutil
    from app.services import metrics

    mk = db.scalar(select(Location).where(Location.code == "MK"))
    rng = random.Random(5)
    for _ in range(80):
        db.add(StockTransaction(item_id=1, location_id=mk.id, txn_type="issue", qty_delta=-1, user_id=1,
                                occurred_at=datetime(2026, 3, 2) + timedelta(days=rng.randint(-3, 3), minutes=rng.randint(0, 1439))))
    db.commit()
    wins = metrics.windows(db, datetime(2026, 3, 3), None, mk.id, datetime(2026, 2, 27).date(), datetime(2026, 3, 5).date())
    moved = metrics.movements(db, wins)
    expected = sorted(timeutil.local_date(t.occurred_at, mk.timezone)
                      for t in db.scalars(select(StockTransaction).where(StockTransaction.location_id == mk.id, StockTransaction.occurred_at >= wins[0].start,
                                                                         StockTransaction.occurred_at < wins[0].end)))
    assert sorted(m.day for m in moved) == expected and all(m.location_id == mk.id and m.item_id == 1 for m in moved if m.txn_type == "issue")


def test_request_copies_are_dropped_when_the_rows_they_came_from_change(db):
    from app.deps import scoped_locations
    from app.models import EmployeeLocation, Employee, User

    user = db.scalar(select(User).where(User.email == "sup.mk@example.test"))
    before = scoped_locations(user, db)
    assert count_queries(lambda: [scoped_locations(user, db) for _ in range(20)]) == 0   # kept after the first call
    emp = db.get(Employee, user.employee.id)
    db.add(EmployeeLocation(employee_id=emp.id, location_id=3))
    db.flush()
    assert scoped_locations(user, db) == before | {3}
    db.rollback()
    assert scoped_locations(user, db) == before


def test_search_keys_follow_the_name_on_every_path(client, login, db):
    from app.services.similarity import compact, token_key

    plate = db.scalar(select(InventoryItem).where(InventoryItem.code == "PL-001"))
    assert (plate.compact_key, plate.token_key) == ("dinnerplate27cm", "27cm dinner plate")      # set for seeded items
    m = login(MGR)
    cat = client.get("/api/inventory/categories", headers=m).json()[0]["id"]
    unit = client.get("/api/inventory/units", headers=m).json()[0]["id"]
    made = client.post("/api/inventory/items", json={"name": "Wine Glasses 35cl", "category_id": cat, "unit_id": unit}, headers=m).json()
    row_ = db.get(InventoryItem, made["id"])
    assert (row_.compact_key, row_.token_key) == (compact("Wine Glasses 35cl"), token_key("Wine Glasses 35cl")) == ("wineglasses35cl", "35cl glass wine")
    client.put(f"/api/inventory/items/{made['id']}", json={"name": "Red Wine Goblet"}, headers=m)
    db.expire_all()
    assert (db.get(InventoryItem, made["id"]).compact_key, db.get(InventoryItem, made["id"]).token_key) == ("redwinegoblet", "goblet red wine")


def test_the_indexed_duplicate_check_refuses_exactly_what_a_full_comparison_would(client, login, db):
    existing = [n for (n,) in db.execute(select(InventoryItem.name))]
    rng = random.Random(21)
    m = login(MGR)
    cat = client.get("/api/inventory/categories", headers=m).json()[0]["id"]
    unit = client.get("/api/inventory/units", headers=m).json()[0]["id"]
    tried = 0
    for base in list(existing):  # a snapshot, because accepted names are added to `existing` as the loop runs
        words = base.split()
        variants = [" ".join(reversed(words)), base.upper(), base.replace(" ", "-"), base.replace(" ", ""), base + "s", base[:-1],
                    " ".join(rng.sample(words, len(words))), base + " extra", "new " + base]
        for name in variants:
            expected = any(classify(name, other) == "same" for other in existing)
            r = client.post("/api/inventory/items", json={"name": name, "category_id": cat, "unit_id": unit}, headers=m)
            assert (r.status_code == 409) == expected, (name, r.status_code)
            tried += 1
            if r.status_code == 201:
                existing.append(name)  # a name that was accepted becomes a candidate for later ones
    assert tried > 80


def test_a_large_item_list_narrows_candidates_but_still_finds_the_obvious_matches(client, login, db, monkeypatch):
    m = login(MGR)
    queries = ["dinner pl", "Dinner Plat 27cm", "27cm plate dinner", "chef kn", "stock pot", "tongs", "gastronorm"]
    everything = {q: [f["code"] for f in client.get(f"/api/inventory/items/lookup?q={q}", headers=m).json()] for q in queries}
    monkeypatch.setattr("app.api.inventory.SCAN_LIMIT", 3)   # as if the list were huge
    narrowed = {q: [f["code"] for f in client.get(f"/api/inventory/items/lookup?q={q}", headers=m).json()] for q in queries}
    assert all(everything[q] for q in queries)
    for q in queries:
        assert narrowed[q][:1] == everything[q][:1], q        # the best match is the same
        assert set(narrowed[q]) <= set(everything[q]) | set(narrowed[q])
