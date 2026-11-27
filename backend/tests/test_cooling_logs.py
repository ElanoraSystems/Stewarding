"""The cooling log (60 °C or above, 21 °C within 2 hours, 5 °C within 6 hours in all) and the hot-holding check."""
from datetime import timedelta

from sqlalchemy import select

from app.models import Notification
from app.services import alerts

from .helpers import MGR, STEWARD, make_lot
from .test_two_step_logs import make


def stage(point, name):
    return next(s for s in point["schedules"] if s["stage"] == name)


def go_in(client, h, point, value=70):
    done = client.post("/api/monitoring/readings/batch", headers=h, json={"equipment_id": point["id"], "readings": [
        {"schedule_id": stage(point, "Time in")["id"], "value": value, "lot_ids": [make_lot(point["location_id"])]}]})
    assert done.status_code == 201, done.text
    return done.json()[0]["id"]


def check(client, h, point, name, value, start_id):
    return client.post("/api/monitoring/readings/batch", headers=h, json={"equipment_id": point["id"], "start_reading_id": start_id,
                                                                          "readings": [{"schedule_id": stage(point, name)["id"], "value": value}]})


def titles(db, kind="time_out_missing"):
    return db.scalars(select(Notification).where(Notification.kind == kind)).all()


def test_the_cooling_template_is_a_critical_control_point_with_two_timed_stages(client, login, db, clock):
    point = make(client, login(MGR), db, "cooling")
    assert point["control_level"] == "ccp"
    start, first, second = (stage(point, n) for n in ("Time in", "Within 2 hours", "Within 6 hours"))
    assert (float(start["min_value"]), start["phase"]) == (60.0, "start")
    assert (float(first["max_value"]), first["max_open_minutes"], first["phase"]) == (21.0, 120, "finish")
    assert (float(second["max_value"]), second["max_open_minutes"]) == (5.0, 360)
    assert start["trace_lots"] is True  # the item or batch is named by choosing its lot or typing what it is
    assert make(client, login(MGR), db, "hot_holding")["control_level"] == "ccp"


def test_the_item_name_is_required_for_a_time_in(client, login, db, clock):
    point = make(client, login(MGR), db, "cooling")
    bare = client.post("/api/monitoring/readings", headers=login(STEWARD), json={"equipment_id": point["id"], "schedule_id": stage(point, "Time in")["id"], "value": 70})
    assert bare.status_code == 400


def test_both_stages_met_in_order_closes_the_entry(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "cooling")
    start = go_in(client, m, point)
    assert [p["stage"] for p in client.get("/api/monitoring/pending", headers=m).json()] == ["Within 2 hours"]
    clock.advance(minutes=110)
    assert check(client, m, point, "Within 2 hours", 20, start).json()[0]["passed"] is True
    assert [p["stage"] for p in client.get("/api/monitoring/pending", headers=m).json()] == ["Within 6 hours"]  # still open for the second stage
    clock.advance(hours=3)
    assert check(client, m, point, "Within 6 hours", 4, start).json()[0]["passed"] is True
    assert client.get("/api/monitoring/pending", headers=m).json() == []
    assert alerts.pending_time_outs(db, clock.now + timedelta(days=2)) == 0


def test_the_second_stage_cannot_be_recorded_before_the_first(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "cooling")
    start = go_in(client, m, point)
    skipped = check(client, m, point, "Within 6 hours", 4, start)
    assert skipped.status_code == 409 and "Within 2 hours" in skipped.json()["detail"]


def test_a_stage_over_its_limit_fails_with_a_corrective_action(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "cooling")
    start = go_in(client, m, point)
    clock.advance(minutes=100)
    late = check(client, m, point, "Within 2 hours", 30, start).json()[0]
    assert late["passed"] is False and late["corrective_action"]["status"] == "action_required"
    assert titles(db, "monitoring_failed")


def test_a_first_stage_not_recorded_in_2_hours_alerts_supervisor_and_manager_critically_once(client, login, db, clock):
    point = make(client, login(MGR), db, "cooling")
    go_in(client, login(STEWARD), point)
    assert alerts.pending_time_outs(db, clock.now + timedelta(minutes=110)) == 0
    assert alerts.pending_time_outs(db, clock.now + timedelta(minutes=125)) > 0
    assert alerts.pending_time_outs(db, clock.now + timedelta(minutes=130)) == 0  # once, not every run
    sent = titles(db)
    assert sent and all(n.priority == "critical" and "CCP Within 2 hours missed" in n.title for n in sent)
    from .test_alerts import emails
    assert {"manager@example.test", "sup.mk@example.test"} <= emails(db, sent)


def test_a_missed_second_stage_alerts_after_6_hours_and_a_met_first_stage_does_not_repeat(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "cooling")
    start = go_in(client, m, point)
    clock.advance(minutes=100)
    check(client, m, point, "Within 2 hours", 18, start)
    assert alerts.pending_time_outs(db, clock.now + timedelta(hours=4)) == 0  # 5 h 40 m in: the 6 hour limit is not reached
    assert alerts.pending_time_outs(db, clock.now + timedelta(hours=4, minutes=30)) > 0
    assert any("Within 6 hours missed" in n.title for n in titles(db))


def test_the_alert_is_high_not_critical_when_the_point_is_not_a_ccp(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "cooling")
    assert client.put(f"/api/equipment/{point['id']}", json={"control_level": "prp"}, headers=m).status_code == 200
    go_in(client, m, point)
    alerts.pending_time_outs(db, clock.now + timedelta(minutes=130))
    assert {n.priority for n in titles(db)} == {"high"}


def test_hot_holding_is_63_degrees_every_two_hours_and_a_missed_check_is_critical(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)  # 12:00 in Dubai, after the 11:00 check has opened
    point = make(client, login(MGR), db, "hot_holding")
    holding = point["schedules"][0]
    assert (float(holding["min_value"]), holding["timing"], holding["interval_minutes"]) == (63.0, "interval", 120)
    from .test_alerts import run
    run(db, clock)
    clock.advance(minutes=40)  # past the grace: the 2 hour check is overdue
    run(db, clock)
    over = [n for n in titles(db, "monitoring_overdue") if point["name"] in n.title]
    assert over and {n.priority for n in over} == {"critical"} and "CCP check overdue" in over[0].title
    low = client.post("/api/monitoring/readings", headers=login(STEWARD), json={"equipment_id": point["id"], "schedule_id": holding["id"], "value": 62})
    assert low.status_code == 201 and low.json()["passed"] is False  # under 63 fails like any reading
