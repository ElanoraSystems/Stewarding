from sqlalchemy import select

from app.models import Notification, TemperatureReading

from .test_checklists import MGR, STEWARD, SUP, find, generate
from .test_monitoring import mk_stage, record

SUP_RB = "sup.rb@example.test"


def complete(client, h, task):
    return client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=h)


def verify(client, h, task, approve=True):
    return client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": approve}, headers=h)


def test_every_completed_checklist_task_waits_for_approval_from_the_supervisor_or_the_manager(client, login, db, clock):
    generate(client, login, db)
    steward = login(STEWARD)
    task = find(client, steward, "Clean drains")  # an ordinary task with no verification flag
    assert complete(client, steward, task).json()["status"] == "pending_verification"
    recipients = {n.user_id for n in db.scalars(select(Notification).where(Notification.kind == "verification_needed"))}
    assert len(recipients) >= 2  # both the supervisor and the manager are asked
    first = verify(client, login(MGR), task)
    assert first.json()["status"] == "verified"
    assert verify(client, login(SUP), task).status_code == 409  # first come, first served
    assert verify(client, login(SUP_RB), task).status_code in (403, 404, 409)


def test_a_supervisor_of_another_location_cannot_approve(client, login, db, clock):
    generate(client, login, db)
    steward = login(STEWARD)
    task = find(client, steward, "Clean drains")
    complete(client, steward, task)
    assert verify(client, login(SUP_RB), task).status_code in (403, 404)
    assert verify(client, login(SUP), task).json()["status"] == "verified"


def test_approval_can_be_switched_off_for_unflagged_tasks(client, login, db, clock):
    assert client.put("/api/settings", json={"values": {"approval.checklists": 0}}, headers=login(MGR)).status_code == 200
    generate(client, login, db)
    steward = login(STEWARD)
    assert complete(client, steward, find(client, steward, "Clean drains")).json()["status"] == "completed"
    assert complete(client, steward, find(client, steward, "Clean dishwasher filters")).json()["status"] == "pending_verification"


def test_readings_are_approved_in_bulk_by_whoever_gets_there_first(client, login, db, clock):
    steward, sup, mgr = login(STEWARD), login(SUP), login(MGR)
    eq, wash = mk_stage(client, steward)
    ids = []
    for _ in range(2):
        ids.append(record(client, steward, eq, wash, 60).json()["id"])
        clock.advance(days=1)
    assert client.post("/api/monitoring/readings/review", json={"reading_ids": ids}, headers=steward).status_code == 403
    done = client.post("/api/monitoring/readings/review", json={"reading_ids": ids}, headers=sup).json()
    assert done == {"reviewed": 2, "skipped": 0}
    again = client.post("/api/monitoring/readings/review", json={"reading_ids": ids}, headers=mgr).json()
    assert again == {"reviewed": 0, "skipped": 2}
    reviewed = db.scalars(select(TemperatureReading)).all()
    assert all(r.reviewed_by and r.reviewed_at for r in reviewed)
    listing = client.get("/api/monitoring/readings", headers=mgr).json()["items"]
    assert {r["reviewed_by_name"] for r in listing} == {"Sam Supervisor"}


def test_you_cannot_approve_your_own_readings_in_bulk(client, login, db, clock):
    sup = login(SUP)
    eq, wash = mk_stage(client, sup)
    mine = record(client, sup, eq, wash, 60).json()["id"]
    done = client.post("/api/monitoring/readings/review", json={"reading_ids": [mine]}, headers=sup).json()
    assert done == {"reviewed": 0, "skipped": 1}
    assert client.post("/api/monitoring/readings/review", json={"reading_ids": []}, headers=sup).status_code == 422


def test_unapproved_readings_show_in_the_pending_list_until_approved(client, login, db, clock):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    rid = record(client, steward, eq, wash, 60).json()["id"]

    def pending():
        items = client.get("/api/notifications/pending-summary", headers=login(MGR)).json()["items"]
        return [i for i in items if i["category"] == "monitoring_review"]

    assert len(pending()) == 1 and "1 monitoring reading" in pending()[0]["description"]
    client.post("/api/monitoring/readings/review", json={"reading_ids": [rid]}, headers=sup)
    assert pending() == []


def test_readings_of_a_switched_off_point_stay_out_of_the_pending_list(client, login, db, clock):
    steward = login(STEWARD)
    eq, wash = mk_stage(client, steward)
    record(client, steward, eq, wash, 60)

    def pending():
        items = client.get("/api/notifications/pending-summary", headers=login(MGR)).json()["items"]
        return [i for i in items if i["category"] == "monitoring_review"]

    assert len(pending()) == 1
    assert client.put(f"/api/equipment/{eq['id']}", json={"active": False}, headers=login(MGR)).status_code == 200
    assert pending() == []


def test_a_task_can_only_be_completed_inside_the_work_area(client, login, db, clock):
    from app.models import Organization
    generate(client, login, db)
    steward = login(STEWARD)
    first, second, third = [t for t in client.get("/api/checklists/instances", headers=steward).json()["items"] if t["status"] in ("not_started", "in_progress", "overdue")][:3]
    done = lambda task, **where: client.post(f"/api/checklists/instances/{task['id']}/complete", json={"late_reason": "Shift changed", **where}, headers=steward)  # noqa: E731
    assert done(first).status_code == 200  # no area set: no position needed
    org = db.get(Organization, 1) or Organization(id=1)
    org.latitude, org.longitude, org.geofence_radius_m = 29.3759, 47.9774, 100
    db.add(org)
    db.commit()
    assert done(second).status_code == 400  # no position sent
    far = done(second, latitude=29.3859, longitude=47.9774)  # about 1.1 km away, "at home"
    assert far.status_code == 403 and "complete checklist tasks only within 100 m" in far.json()["detail"]
    assert done(second, latitude=29.3760, longitude=47.9775).status_code == 200  # about 15 m away
    assert done(third, latitude=29.3760, longitude=47.9775).status_code == 200
