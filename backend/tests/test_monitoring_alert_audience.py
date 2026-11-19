from sqlalchemy import select

from app.models import User

from .helpers import MGR, STEWARD, SUP
from .test_alerts import emails, notes, run


def point(client, login):
    return next(e for e in client.get("/api/monitoring/equipment", headers=login(STEWARD)).json() if e["code"] == "DW-MK-1")


def fail(client, h, eq):
    sched = next(s for s in eq["schedules"] if s["stage"] == "wash")
    return client.post("/api/monitoring/readings", headers=h, json={"equipment_id": eq["id"], "schedule_id": sched["id"], "value": 40, "corrective_action": "Refilled the tank"})


def uid(db, email):
    return db.scalar(select(User.id).where(User.email == email))


def test_a_failed_check_goes_to_the_logs_job_titles_and_managers(client, login, db, clock):
    eq = point(client, login)
    assert client.put(f"/api/equipment/{eq['id']}", json={"visible_to": ["Steward"]}, headers=login(MGR)).status_code == 200  # the supervisor's job title is not among them
    assert fail(client, login(STEWARD), eq).status_code == 201
    assert emails(db, notes(db, "monitoring_failed")) == {"manager@example.test"}  # the supervisor is no longer told about a log that is not theirs


def test_the_named_reviewers_are_added_to_the_failure_alert_whatever_their_job_title(client, login, db, clock):
    eq = point(client, login)
    m = login(MGR)
    client.put(f"/api/equipment/{eq['id']}", json={"visible_to": ["Steward"], "approvers": [uid(db, SUP)]}, headers=m)
    assert fail(client, login(STEWARD), eq).status_code == 201
    assert emails(db, notes(db, "monitoring_failed")) == {"manager@example.test", "sup.mk@example.test"}


def test_a_log_with_nothing_chosen_alerts_its_usual_recipients(client, login, db, clock):
    eq = point(client, login)
    fail(client, login(STEWARD), eq)
    assert emails(db, notes(db, "monitoring_failed")) == {"manager@example.test", "sup.mk@example.test"}


def test_the_overdue_notice_follows_the_same_rule(client, login, db, clock):
    eq = point(client, login)
    client.put(f"/api/equipment/{eq['id']}", json={"visible_to": ["Steward"]}, headers=login(MGR))
    run(db, clock)
    clock.advance(minutes=40)  # past the grace, the wash check is overdue
    run(db, clock)
    over = [n for n in notes(db, "monitoring_overdue") if "Main Kitchen Dishwasher 1" in n.title]
    assert over and emails(db, over) == {"manager@example.test"}
    client.put(f"/api/equipment/{eq['id']}", json={"approvers": [uid(db, SUP)]}, headers=login(MGR))
    clock.advance(minutes=5)
    run(db, clock)  # the same slot is not raised again for the people already told, so the reviewer is told for later slots
    assert emails(db, [n for n in notes(db, "monitoring_overdue") if "Main Kitchen Dishwasher 1" in n.title]) >= {"manager@example.test"}


def test_named_reviewers_are_told_when_a_reading_is_recorded_once_an_hour_and_never_the_recorder(client, login, db, clock):
    eq = point(client, login)
    checks = [s for s in eq["schedules"] if s["active"]][:2]
    assert len(checks) == 2
    m, steward = login(MGR), login(STEWARD)

    def record(check, value):
        return client.post("/api/monitoring/readings", headers=steward, json={"equipment_id": eq["id"], "schedule_id": check["id"], "value": value})

    assert record(checks[0], 60).status_code == 201 and notes(db, "review_needed") == []  # nobody is named, so no review alert
    assert client.put(f"/api/equipment/{eq['id']}", json={"approvers": [uid(db, STEWARD)]}, headers=m).status_code == 400  # a steward cannot review
    assert client.put(f"/api/equipment/{eq['id']}", json={"approvers": [uid(db, SUP)]}, headers=m).status_code == 200
    first = record(checks[1], 60)
    assert first.status_code == 201
    got = notes(db, "review_needed")
    assert len(got) == 1 and emails(db, got) == {"sup.mk@example.test"} and "Review:" in got[0].title
    clock.advance(minutes=10)
    record(checks[1], 61)  # a second reading in the same hour adds nothing new
    assert len(notes(db, "review_needed")) == 1
