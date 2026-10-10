from datetime import timedelta

from sqlalchemy import select

from app.models import ApprovalRecord, Notification, StockTransaction

from .helpers import MGR, STEWARD, SUP, SUP_RB, balance, item_id, ledger_sum, loc_id


def transfer(client, h, db, qty=10, code="PL-001", src="MK", dst="BQ"):
    body = {"from_location_id": loc_id(db, src), "to_location_id": loc_id(db, dst),
            "lines": [{"item_id": item_id(db, code), "qty": qty}], "note": "Banquet setup"}
    return client.post("/api/stock/transfers", json=body, headers=h)


def decide(client, h, transfer_id, approve=True):
    return client.post(f"/api/stock/transfers/{transfer_id}/decision", json={"approve": approve, "note": "ok"}, headers=h)


def test_supervisor_request_waits_for_manager_and_moves_nothing(client, login, db):
    r = transfer(client, login(SUP), db)
    assert r.status_code == 201 and r.json()["status"] == "requested"
    assert balance(db, "PL-001", "MK") == 200 and balance(db, "PL-001", "BQ") == 150
    assert db.scalar(select(Notification.id).where(Notification.kind == "transfer_pending"))


def test_approval_posts_both_sides_atomically_and_only_once(client, login, db):
    t = transfer(client, login(SUP), db).json()
    assert decide(client, login(SUP), t["id"]).status_code == 403
    assert decide(client, login(MGR), t["id"]).json()["status"] == "completed"
    assert balance(db, "PL-001", "MK") == 190 and balance(db, "PL-001", "BQ") == 160
    kinds = {x.txn_type: x.ref_id for x in db.scalars(select(StockTransaction).where(StockTransaction.ref_type == "transfer"))}
    assert kinds == {"transfer_out": t["id"], "transfer_in": t["id"]}
    assert decide(client, login(MGR), t["id"]).status_code == 409
    assert balance(db, "PL-001", "MK") == ledger_sum(db, "PL-001", "MK") == 190
    assert db.scalar(select(ApprovalRecord.id).where(ApprovalRecord.subject_type == "transfer"))


def test_transfer_larger_than_stock_stays_requested(client, login, db):
    t = transfer(client, login(SUP), db, qty=500).json()
    assert decide(client, login(MGR), t["id"]).status_code == 409
    assert balance(db, "PL-001", "MK") == 200 and balance(db, "PL-001", "BQ") == 150
    listing = client.get("/api/stock/transfers?transfer_status=requested", headers=login(MGR)).json()
    assert [x["id"] for x in listing] == [t["id"]]


def test_rejected_transfer_changes_no_stock(client, login, db):
    t = transfer(client, login(SUP), db).json()
    assert decide(client, login(MGR), t["id"], approve=False).json()["status"] == "rejected"
    assert balance(db, "PL-001", "MK") == 200
    assert db.scalar(select(Notification.id).where(Notification.kind == "transfer_rejected"))


def test_transfer_scope_rules(client, login, db):
    assert transfer(client, login(SUP_RB), db).status_code == 403   # RB supervisor cannot send from MK
    assert transfer(client, login(STEWARD), db).status_code == 403
    assert transfer(client, login(SUP), db, src="MK", dst="MK").status_code == 400
    assert transfer(client, login(SUP), db, dst="BQ", qty=-1).status_code == 422


def test_manager_requested_transfer_executes_immediately(client, login, db):
    r = transfer(client, login(MGR), db, qty=20)
    assert r.json()["status"] == "completed"
    assert balance(db, "PL-001", "MK") == 180 and balance(db, "PL-001", "BQ") == 170


def test_supervisor_sees_transfers_touching_their_locations_only(client, login, db):
    transfer(client, login(MGR), db, qty=5, src="BQ", dst="RB")
    assert len(client.get("/api/stock/transfers", headers=login(SUP_RB)).json()) == 1
    assert len(client.get("/api/stock/transfers", headers=login(SUP)).json()) == 1  # BQ is theirs


def count(client, h, db, counted, code="PL-001", loc="MK", kind="crockery"):
    body = {"location_id": loc_id(db, loc), "kind": kind, "lines": [{"item_id": item_id(db, code), "counted_qty": counted}]}
    return client.post("/api/stock/counts", json=body, headers=h)


def test_count_with_variance_needs_manager_and_posts_one_adjustment(client, login, db):
    c = count(client, login(SUP), db, 190).json()
    assert c["lines"][0]["system_qty"] == 200 and c["lines"][0]["variance"] == -10
    assert client.post(f"/api/stock/counts/{c['id']}/post", headers=login(SUP)).status_code == 403
    assert balance(db, "PL-001", "MK") == 200
    posted = client.post(f"/api/stock/counts/{c['id']}/post", headers=login(MGR)).json()
    assert posted["status"] == "posted" and posted["lines"][0]["adjustment_txn_id"]
    assert balance(db, "PL-001", "MK") == 190 == ledger_sum(db, "PL-001", "MK")
    assert client.post(f"/api/stock/counts/{c['id']}/post", headers=login(MGR)).status_code == 409


def test_count_without_variance_can_be_posted_by_supervisor(client, login, db):
    c = count(client, login(SUP), db, 200).json()
    assert client.post(f"/api/stock/counts/{c['id']}/post", headers=login(SUP)).json()["status"] == "posted"
    assert db.scalars(select(StockTransaction).where(StockTransaction.ref_type == "count")).all() == []


def test_count_validation_and_scope(client, login, db):
    assert count(client, login(STEWARD), db, 5).status_code == 403
    assert count(client, login(SUP_RB), db, 5).status_code == 403
    assert count(client, login(SUP), db, 5, code="KN-001", kind="crockery").status_code == 400
    assert count(client, login(SUP), db, -1).status_code == 422
    dup = {"location_id": loc_id(db, "MK"), "kind": "crockery",
           "lines": [{"item_id": item_id(db, "PL-001"), "counted_qty": 1}] * 2}
    assert client.post("/api/stock/counts", json=dup, headers=login(SUP)).status_code == 400


def test_monthly_reconciliation_adds_up_and_carries_forward(client, login, db, clock):
    h, m = login(SUP), login(MGR)
    base = {"item_id": item_id(db, "PL-001"), "location_id": loc_id(db, "MK")}
    clock.advance(hours=1)
    client.post("/api/inventory/transactions", json={**base, "txn_type": "receipt", "qty": 30}, headers=h)
    client.post("/api/inventory/transactions", json={**base, "txn_type": "issue", "qty": 20}, headers=h)
    client.post("/api/inventory/transactions", json={**base, "txn_type": "damage", "qty": 4, "reason": "Dropped tray"}, headers=h)
    c = count(client, h, db, 200).json()  # system is 206
    client.post(f"/api/stock/counts/{c['id']}/post", headers=m)
    url = f"/api/stock/reconciliation?location_id={loc_id(db, 'MK')}&kind=crockery&month=2026-03"
    row_ = next(r for r in client.get(url, headers=h).json()["rows"] if r["code"] == "PL-001")
    assert (row_["opening_stock"], row_["receipts"], row_["issues"], row_["breakage_damage"], row_["adjustments"]) == (200, 30, -20, -4, -6)
    assert row_["closing"] == 200 == balance(db, "PL-001", "MK")
    assert row_["counted_qty"] == 200 and row_["count_variance"] == -6
    clock.advance(days=40)
    april = next(r for r in client.get(url.replace("2026-03", "2026-04"), headers=h).json()["rows"] if r["code"] == "PL-001")
    assert april["opening"] == 200 and april["closing"] == 200


def test_reconciliation_validation_and_scope(client, login, db):
    base = f"/api/stock/reconciliation?location_id={loc_id(db, 'MK')}&kind=crockery"
    assert client.get(base + "&month=2026-13", headers=login(MGR)).status_code == 400
    assert client.get(base + "&month=2026-03", headers=login(SUP_RB)).status_code == 403
    assert client.get(base + "&month=2026-03", headers=login(STEWARD)).status_code == 200
