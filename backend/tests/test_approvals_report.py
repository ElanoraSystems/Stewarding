from datetime import date, timedelta

from sqlalchemy import select

from app.models import Notification, User

from .test_checklists import MGR, STEWARD, SUP, find, generate, loc_id
from .test_monitoring import mk_stage, record


def approvals(client, h, db, **params):
    query = "&".join(f"{k}={v}" for k, v in {"location_id": loc_id(db, "MK"), "date_from": str(date.today() - timedelta(days=1)), "date_to": str(date.today() + timedelta(days=1)), **params}.items())
    doc = client.get(f"/api/reports/records/approvals?{query}", headers=h).json()
    return [r for g in doc["groups"] for r in g["rows"]]


def alert(db, email, **extra):
    user = db.scalar(select(User).where(User.email == email))
    n = Notification(user_id=user.id, kind="check_overdue", title="Check overdue: Chiller", dedupe_key=f"t{extra.pop('n', 1)}", requires_ack=True,
                     location_id=loc_id(db, "MK"), **extra)
    db.add(n)
    db.commit()
    return n.id


def test_checklist_approvals_and_rejections_keep_their_comments_for_the_report(client, login, db, clock):
    generate(client, login, db)
    steward, sup = login(STEWARD), login(SUP)
    a, b = find(client, steward, "Clean drains"), find(client, steward, "Clean dishwasher filters")
    for t in (a, b):
        assert client.post(f"/api/checklists/instances/{t['id']}/complete", json={}, headers=steward).status_code == 200
    assert client.post(f"/api/checklists/instances/{a['id']}/verify", json={"approve": True, "comment": "Spotless"}, headers=sup).status_code == 200
    assert client.post(f"/api/checklists/instances/{b['id']}/verify", json={"approve": False}, headers=sup).status_code == 400  # a rejection needs a comment
    assert client.post(f"/api/checklists/instances/{b['id']}/verify", json={"approve": False, "comment": "Filter still dirty"}, headers=sup).status_code == 200
    rows = approvals(client, login(MGR), db)
    assert [(r["decision"], r["comment"]) for r in rows] == [("Approved", "Spotless"), ("Rejected", "Filter still dirty")]
    assert all(r["kind"] == "Checklist task" and r["by"] for r in rows)
    assert [r["decision"] for r in approvals(client, login(MGR), db, status="rejected")] == ["Rejected"]


def test_monitoring_readings_approved_with_a_comment_or_rejected_with_a_reason_are_reported(client, login, db, clock):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    _, rinse = mk_stage(client, steward, "final_rinse")
    first, second = (record(client, steward, eq, st, v).json()["id"] for st, v in ((wash, 60.0), (rinse, 85.0)))
    assert client.post(f"/api/monitoring/readings/{first}/review", json={"comment": "Looks right"}, headers=sup).status_code == 200
    assert client.post("/api/monitoring/readings/reject", json={"reading_ids": [second], "reason": "Wrong probe used"}, headers=sup).status_code == 200
    rows = approvals(client, login(MGR), db)
    assert [(r["kind"], r["decision"], r["comment"]) for r in rows] == [("Monitoring reading", "Approved", "Looks right"), ("Monitoring reading", "Rejected", "Wrong probe used")]


def test_an_alert_can_be_approved_or_rejected_with_a_comment_and_the_list_can_be_cleared(client, login, db, clock):
    sup = login(SUP)
    one, two, three = alert(db, SUP, n=1), alert(db, SUP, n=2), alert(db, SUP, n=3)
    assert client.post(f"/api/notifications/{one}/acknowledge", json={"decision": "rejected"}, headers=sup).status_code == 422  # a rejection needs a comment
    assert client.post(f"/api/notifications/{one}/acknowledge", json={"decision": "rejected", "comment": "Not our point"}, headers=sup).status_code == 200
    assert client.post(f"/api/notifications/{two}/acknowledge", headers=sup).status_code == 200  # a plain approve still works
    rows = approvals(client, login(MGR), db)
    assert [(r["kind"], r["decision"], r["comment"]) for r in rows] == [("Alert", "Rejected", "Not our point"), ("Alert", "Approved", "")]
    cleared = client.post("/api/notifications/clear", headers=sup).json()["cleared"]
    left = client.get("/api/notifications", headers=sup).json()["items"]
    assert cleared >= 2 and [n["id"] for n in left] == [three]  # the one still waiting for a decision stays
    done = client.post("/api/notifications/acknowledge-many", json={"decision": "approved", "comment": "Seen to"}, headers=sup).json()
    assert done == {"acknowledged": 1} and approvals(client, login(MGR), db)[-1]["comment"] == "Seen to"
