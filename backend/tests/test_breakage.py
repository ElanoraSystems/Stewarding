from sqlalchemy import select

from app.models import ApprovalRecord, BreakageIncident, Notification, StockTransaction

from .helpers import MGR, STEWARD, STEWARD_RB, SUP, SUP_RB, balance, item_id, ledger_sum, loc_id


def report(client, h, db, qty=2, code="PL-001", loc="MK", kind="breakage", **extra):
    body = {"location_id": loc_id(db, loc), "item_id": item_id(db, code), "qty": qty, "incident_type": kind,
            "reason": "Slipped while stacking", **extra}
    return client.post("/api/breakage", json=body, headers=h)


def review(client, h, incident_id, qty=2, **extra):
    return client.post(f"/api/breakage/{incident_id}/review", json={"qty": qty, **extra}, headers=h)


def test_reporting_alerts_the_supervisor_and_does_not_touch_stock(client, login, db):
    r = report(client, login(STEWARD), db)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "reported" and body["code"].startswith("BRK-") and body["est_cost"] == 5.0
    assert balance(db, "PL-001", "MK") == 200
    assert db.scalar(select(Notification.id).where(Notification.kind == "breakage_review"))


def test_small_incident_is_deducted_once_through_a_linked_transaction(client, login, db):
    incident = report(client, login(STEWARD), db).json()
    done = review(client, login(SUP), incident["id"], preventive_action="Use stacking racks").json()
    assert done["status"] == "approved" and done["transaction_id"]
    assert balance(db, "PL-001", "MK") == 198 == ledger_sum(db, "PL-001", "MK")
    txn = db.get(StockTransaction, done["transaction_id"])
    assert txn.txn_type == "breakage" and txn.ref_type == "breakage" and txn.ref_id == incident["id"]
    assert review(client, login(SUP), incident["id"]).status_code == 409
    assert client.post(f"/api/breakage/{incident['id']}/approve", json={}, headers=login(MGR)).status_code == 409
    assert balance(db, "PL-001", "MK") == 198


def test_reviewer_can_correct_the_quantity(client, login, db):
    incident = report(client, login(STEWARD), db, qty=4).json()
    done = review(client, login(SUP), incident["id"], qty=3).json()
    assert done["qty"] == 3 and done["est_cost"] == 7.5
    assert balance(db, "PL-001", "MK") == 197


def test_large_quantity_waits_for_manager_approval(client, login, db):
    incident = report(client, login(STEWARD), db, qty=6).json()
    pending = review(client, login(SUP), incident["id"], qty=6).json()
    assert pending["status"] == "pending_approval" and pending["transaction_id"] is None
    assert balance(db, "PL-001", "MK") == 200
    assert db.scalar(select(Notification.id).where(Notification.kind == "breakage_approval"))
    url = f"/api/breakage/{incident['id']}/approve"
    assert client.post(url, json={}, headers=login(SUP)).status_code == 403
    assert client.post(url, json={}, headers=login(STEWARD)).status_code == 403
    assert client.post(url, json={"note": "Confirmed"}, headers=login(MGR)).json()["status"] == "approved"
    assert balance(db, "PL-001", "MK") == 194
    assert client.post(url, json={}, headers=login(MGR)).status_code == 409
    assert balance(db, "PL-001", "MK") == 194 == ledger_sum(db, "PL-001", "MK")
    assert db.scalar(select(ApprovalRecord.id).where(ApprovalRecord.subject_type == "breakage"))


def test_high_cost_triggers_approval_even_below_the_quantity_threshold(client, login, db):
    incident = report(client, login(STEWARD), db, qty=3, code="PN-001").json()  # 3 x 48 = 144
    assert review(client, login(SUP), incident["id"], qty=3).json()["status"] == "pending_approval"


def test_nobody_reviews_their_own_report(client, login, db):
    incident = report(client, login(SUP), db).json()
    assert review(client, login(SUP), incident["id"]).status_code == 403
    assert review(client, login(MGR), incident["id"]).json()["status"] == "approved"


def test_missing_items_post_a_negative_adjustment(client, login, db):
    incident = report(client, login(STEWARD), db, qty=3, kind="missing").json()
    done = review(client, login(SUP), incident["id"], qty=3).json()
    assert db.get(StockTransaction, done["transaction_id"]).txn_type == "adjustment"
    assert balance(db, "PL-001", "MK") == 197 == ledger_sum(db, "PL-001", "MK")


def test_rejection_leaves_stock_alone_and_is_final(client, login, db):
    incident = report(client, login(STEWARD), db).json()
    url = f"/api/breakage/{incident['id']}/reject"
    assert client.post(url, json={"reason": "no"}, headers=login(SUP)).status_code == 422
    assert client.post(url, json={"reason": "Counted wrongly"}, headers=login(STEWARD)).status_code == 403
    assert client.post(url, json={"reason": "Counted wrongly"}, headers=login(SUP)).json()["status"] == "rejected"
    assert balance(db, "PL-001", "MK") == 200
    assert client.post(url, json={"reason": "Counted wrongly"}, headers=login(SUP)).status_code == 409
    assert review(client, login(SUP), incident["id"]).status_code == 409


def test_only_a_manager_rejects_an_incident_awaiting_approval(client, login, db):
    incident = report(client, login(STEWARD), db, qty=6).json()
    review(client, login(SUP), incident["id"], qty=6)
    url = f"/api/breakage/{incident['id']}/reject"
    assert client.post(url, json={"reason": "Not credible"}, headers=login(SUP)).status_code == 403
    assert client.post(url, json={"reason": "Not credible"}, headers=login(MGR)).json()["status"] == "rejected"


def test_location_isolation(client, login, db):
    assert report(client, login(STEWARD_RB), db).status_code == 403
    incident = report(client, login(STEWARD), db).json()
    assert review(client, login(SUP_RB), incident["id"]).status_code == 403
    assert client.get("/api/breakage", headers=login(SUP_RB)).json()["total"] == 0
    assert client.get("/api/breakage", headers=login(SUP)).json()["total"] == 1


def test_steward_sees_only_own_incidents(client, login, db):
    report(client, login(STEWARD), db)
    report(client, login(SUP), db)
    assert client.get("/api/breakage", headers=login(STEWARD)).status_code == 403
    assert len(client.get("/api/breakage/mine", headers=login(STEWARD)).json()) == 1


def test_breakage_may_drive_stock_negative_and_flags_low_stock(client, login, db):
    incident = report(client, login(STEWARD), db, qty=10, code="UT-001", loc="MK").json()
    review(client, login(SUP), incident["id"], qty=10)
    client.post(f"/api/breakage/{incident['id']}/approve", json={}, headers=login(MGR))
    assert balance(db, "UT-001", "MK") == 2 == ledger_sum(db, "UT-001", "MK")
    big = report(client, login(STEWARD), db, qty=9, code="UT-001", loc="MK").json()
    review(client, login(SUP), big["id"], qty=9)
    client.post(f"/api/breakage/{big['id']}/approve", json={}, headers=login(MGR))
    assert balance(db, "UT-001", "MK") == -7
    assert db.scalar(select(Notification.id).where(Notification.kind == "low_stock"))


def test_list_filters(client, login, db):
    a = report(client, login(STEWARD), db).json()
    report(client, login(STEWARD), db, kind="damage", code="BW-001")
    review(client, login(SUP), a["id"])
    m = login(MGR)
    assert client.get("/api/breakage?incident_status=approved", headers=m).json()["total"] == 1
    assert client.get("/api/breakage?incident_type=damage", headers=m).json()["total"] == 1
    assert client.get(f"/api/breakage?item_id={item_id(db, 'BW-001')}", headers=m).json()["total"] == 1


def test_invalid_reports_are_rejected(client, login, db):
    h = login(STEWARD)
    assert report(client, h, db, qty=0).status_code == 422
    assert report(client, h, db, kind="stolen").status_code == 422
    assert report(client, h, db, photo_path="0" * 32 + ".png").status_code == 400
    assert client.post("/api/breakage", json={"location_id": 1, "item_id": 9999, "qty": 1, "incident_type": "damage"}, headers=h).status_code == 404
    assert db.scalars(select(BreakageIncident)).all() == []
