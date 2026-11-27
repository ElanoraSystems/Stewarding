from datetime import timedelta

from sqlalchemy import select

from app import timeutil
from app.models import ChecklistInstance, ChecklistTask, ChecklistTemplate, Equipment, EquipmentSchedule, Location, TemperatureReading
from app.services import compliance, metrics

from .helpers import MGR, STEWARD, SUP, SUP_RB, loc_id


TODAY = {"date_from": "2026-03-02", "date_to": "2026-03-02"}


def view(client, h, **params):
    r = client.get("/api/dashboard/compliance", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def generate(client, login, db, code="MK"):
    client.post("/api/checklists/generate", json={"location_id": loc_id(db, code)}, headers=login(MGR))
    return list(db.scalars(select(ChecklistInstance).where(ChecklistInstance.location_id == loc_id(db, code)).order_by(ChecklistInstance.id)))


def mk_row(body, db):
    return next(o for o in body["outlets"] if o["location_id"] == loc_id(db, "MK"))


def point(client, h, code="DW-MK-1"):
    return next(e for e in client.get("/api/monitoring/equipment", headers=h).json() if e["code"] == code)


def record(client, h, eq, stage, value, **extra):
    return client.post("/api/monitoring/readings", headers=h, json={"equipment_id": eq["id"], "schedule_id": next(s for s in eq["schedules"] if s["stage"] == stage)["id"], "value": value, **extra})


def test_task_on_time_counts_grace_late_failed_overdue_and_leaves_out_waived_and_future(client, login, db, clock):
    tasks = generate(client, login, db)
    now = clock.now
    done_on_time, done_in_grace, done_late, still_open, waived, future = tasks[:6]
    for t, due, state, done in ((done_on_time, now - timedelta(hours=3), "completed", now - timedelta(hours=4)),
                                (done_in_grace, now - timedelta(hours=3), "verified", now - timedelta(hours=3) + timedelta(minutes=10)),
                                (done_late, now - timedelta(hours=3), "pending_verification", now - timedelta(hours=3) + timedelta(minutes=40)),
                                (still_open, now - timedelta(hours=2), "not_started", None),
                                (waived, now - timedelta(hours=2), "waived", None),
                                (future, now + timedelta(hours=5), "not_started", None)):
        t.due_at, t.status, t.completed_at = due, state, done
    for t in tasks[6:]:
        t.status = "waived"  # leave the rest of the day out so the numbers are the six above
    db.commit()
    row = mk_row(view(client, login(MGR)), db)
    assert row["checklists"] == {"due": 4, "on_time": 2, "percent": 50.0}  # on time and in grace; late and open past due do not count
    assert sum(row["missed_by_hour"]["tasks"]) == 2  # the late one and the open one, each in the hour it was due


def test_a_task_with_no_time_or_shift_is_due_at_the_day_end_rule(client, login, db, clock):
    chosen = db.scalar(select(ChecklistTask).join(ChecklistTemplate, ChecklistTemplate.id == ChecklistTask.template_id).where(
        ChecklistTemplate.location_id == loc_id(db, "MK"), ChecklistTemplate.frequency == "daily", ChecklistTask.weekdays.like("%0%")))
    chosen.deadline_time = chosen.shift_id = None  # neither a time nor a shift
    db.commit()
    tasks = generate(client, login, db)
    plain = next(t for t in tasks if t.task_id == chosen.id)
    for t in tasks:
        t.status = "waived"
    plain.status = "completed"
    db.commit()
    due_local = timeutil.to_local(plain.due_at, "Asia/Dubai")
    assert (due_local.hour, due_local.date() - plain.local_date) == (6, timedelta(days=1))  # 06:00 the next morning
    clock.set(2026, 3, 3, 4, 0)  # past 06:00 Dubai the next morning, so the task is judged
    plain.completed_at = plain.due_at - timedelta(minutes=30)
    db.commit()
    assert mk_row(view(client, login(MGR), date_from="2026-03-02", date_to="2026-03-02"), db)["checklists"] == {"due": 1, "on_time": 1, "percent": 100.0}
    plain.completed_at = plain.due_at + timedelta(minutes=16)  # past the 15 minute grace
    db.commit()
    assert mk_row(view(client, login(MGR), date_from="2026-03-02", date_to="2026-03-02"), db)["checklists"] == {"due": 1, "on_time": 0, "percent": 0.0}


def test_nothing_due_gives_no_percentage_rather_than_a_division_by_zero(client, login, db, clock):
    clock.set(2026, 3, 2, 0, 0)  # 04:00 in Dubai, before anything is due
    row = mk_row(view(client, login(MGR), **TODAY), db)
    assert row["checklists"] == {"due": 0, "on_time": 0, "percent": None}
    assert row["monitoring"]["percent"] is None and sum(row["missed_by_hour"]["tasks"]) == 0


def test_missed_monitoring_checks_are_counted_by_the_hour_they_were_due(client, login, db, clock):
    clock.set(2026, 3, 2, 6, 0)  # 10:00 in Dubai, nothing recorded yet
    row = mk_row(view(client, login(MGR)), db)
    mon = row["monitoring"]
    assert mon["missed"] > 0 and mon["done"] == 0 and mon["percent"] == 0.0
    hours = row["missed_by_hour"]["monitoring"]
    assert len(hours) == 24 and sum(hours) == mon["missed"]
    assert not any(hours[11:])  # nothing is missed in an hour that has not come yet


def test_ccp_checks_are_shown_apart_from_the_rest_and_failed_readings_are_counted(client, login, db, clock):
    clock.set(2026, 3, 2, 2, 45)
    steward = login(STEWARD)
    eq = point(client, steward)
    assert record(client, steward, eq, "wash", 20, corrective_action="Rewashed the load").status_code == 201  # below the limit
    record(client, steward, eq, "final_rinse", 90)
    db.get(Equipment, eq["id"]).control_level = "ccp"
    db.commit()
    row = mk_row(view(client, login(MGR), **TODAY), db)
    assert row["failed_readings"] == row["monitoring"]["failed"] >= 1
    assert row["ccp"]["due"] == 2 and row["ccp"]["done"] == 2 and row["ccp"]["failed"] == row["failed_readings"]
    assert row["monitoring"]["due"] == 4 > row["ccp"]["due"]  # the other dishwasher-type point at this outlet is not a CCP
    assert row["open_actions"] >= 1
    db.get(Equipment, eq["id"]).control_level = "prp"
    db.commit()
    assert mk_row(view(client, login(MGR), **TODAY), db)["ccp"] == {"done": 0, "due": 0, "missed": 0, "failed": 0, "percent": None}


def test_overdue_now_and_probes_needing_calibration(client, login, db, clock):
    tasks = generate(client, login, db)
    for t in tasks:
        t.status, t.due_at = "not_started", clock.now + timedelta(hours=3)
    tasks[0].due_at = clock.now - timedelta(hours=2)
    tasks[1].due_at = clock.now - timedelta(minutes=5)  # inside the grace period: not overdue yet
    db.commit()
    manager = login(MGR)
    assert mk_row(view(client, manager), db)["overdue_now"] == 1
    probe = client.post("/api/calibration/probes", headers=manager, json={"code": "TH-MK-1", "name": "Probe one", "location_id": loc_id(db, "MK")}).json()
    assert mk_row(view(client, manager), db)["probes"] == {"total": 1, "needs_calibration": 1, "due_soon": 0}
    client.post(f"/api/calibration/probes/{probe['id']}/calibrations", json={"method": "ice_point", "reading_c": 0.2}, headers=manager)
    assert mk_row(view(client, manager), db)["probes"] == {"total": 1, "needs_calibration": 0, "due_soon": 0}


def test_a_manager_sees_every_outlet_and_a_supervisor_only_their_own(client, login, db):
    assert {o["location_id"] for o in view(client, login(MGR))["outlets"]} == set(db.scalars(select(Location.id).where(Location.active.is_(True))))
    assert {o["location_id"] for o in view(client, login(SUP))["outlets"]} == {loc_id(db, "MK"), loc_id(db, "BQ")}  # the supervisor's two outlets, not Rooftop
    assert [o["location_id"] for o in view(client, login(SUP_RB))["outlets"]] == [loc_id(db, "RB")]
    assert client.get("/api/dashboard/compliance", params={"location_id": loc_id(db, "RB")}, headers=login(SUP)).status_code == 403
    assert client.get("/api/dashboard/compliance", headers=login(STEWARD)).status_code == 403


def test_points_and_checklists_hidden_from_a_job_title_stay_out_of_the_numbers(db, clock):
    clock.set(2026, 3, 2, 6, 0)
    now = clock.now
    win = metrics.windows(db, now, None, loc_id(db, "MK"), now.date(), now.date())
    everything = compliance.outlet_compliance(db, win, now, set(), set())[0]
    ids = set(db.scalars(select(Equipment.id).where(Equipment.location_id == loc_id(db, "MK"))))
    templates = {t for (t,) in db.execute(select(ChecklistTask.template_id).distinct())}
    narrowed = compliance.outlet_compliance(db, win, now, templates, ids)[0]
    assert everything["monitoring"]["due"] > 0 and narrowed["monitoring"]["due"] == 0
    assert narrowed["checklists"]["due"] == 0 and narrowed["overdue_now"] == 0


def test_a_viewer_without_checklists_or_monitoring_gets_only_what_they_may_open(db, clock):
    now = clock.now
    win = metrics.windows(db, now, None, loc_id(db, "MK"), now.date(), now.date())
    row = compliance.outlet_compliance(db, win, now, set(), set(), checklists=False, monitoring=True)[0]
    assert row["checklists"] is None and row["overdue_now"] is None and row["monitoring"] is not None
    row = compliance.outlet_compliance(db, win, now, set(), set(), checklists=True, monitoring=False)[0]
    assert row["monitoring"] is None and row["probes"] is None and row["checklists"] is not None


def test_the_period_defaults_to_seven_days_and_is_bounded(client, login):
    assert view(client, login(MGR))["range"] == {"date_from": "2026-02-24", "date_to": "2026-03-02"}
    assert view(client, login(MGR), days=30)["range"]["date_from"] == "2026-02-01"
    assert client.get("/api/dashboard/compliance", params={"days": 94}, headers=login(MGR)).status_code == 422
    assert client.get("/api/dashboard/compliance", params={"date_from": "2025-01-01"}, headers=login(MGR)).status_code == 400
    assert client.get("/api/dashboard/compliance", params={"date_from": "2026-03-05", "date_to": "2026-03-01"}, headers=login(MGR)).status_code == 400


def trend(client, h, eq, stage, **params):
    sched = next(s for s in eq["schedules"] if s["stage"] == stage)
    return client.get("/api/monitoring/trend", params={"equipment_id": eq["id"], "schedule_id": sched["id"], **params}, headers=h)


def test_trend_lists_readings_oldest_first_with_the_limits_and_marks_failures(client, login, db, clock):
    steward = login(STEWARD)
    eq = point(client, steward)
    clock.set(2026, 3, 2, 2, 45)
    assert record(client, steward, eq, "wash", 60).status_code == 201
    first = db.scalar(select(TemperatureReading).where(TemperatureReading.equipment_id == eq["id"]))
    columns = {c.name: getattr(first, c.name) for c in TemperatureReading.__table__.columns if c.name != "id"}
    for hours, value, passed in ((3, 62, True), (1, 20, False)):  # added out of order: the trend sorts them by time
        db.add(TemperatureReading(**columns | {"value": value, "passed": passed, "recorded_at": clock.now - timedelta(hours=hours)}))
    db.commit()
    sched = db.get(EquipmentSchedule, next(s["id"] for s in eq["schedules"] if s["stage"] == "wash"))
    sched.warn_max = sched.max_value
    db.commit()
    body = trend(client, steward, eq, "wash", days=7).json()
    assert [p["value"] for p in body["points"]] == [62.0, 20.0, 60.0]
    assert [p["passed"] for p in body["points"]] == [True, False, True]
    assert body["min_value"] == float(sched.min_value) and body["max_value"] == float(sched.max_value) and body["warn_max"] == float(sched.warn_max)
    assert body["warn_min"] is None and body["truncated"] is False


def test_trend_leaves_out_rejected_and_old_readings_and_is_bounded(client, login, db, clock, monkeypatch):
    steward = login(STEWARD)
    eq = point(client, steward)
    clock.set(2026, 3, 2, 2, 45)
    record(client, steward, eq, "wash", 70)
    first = db.scalar(select(TemperatureReading).where(TemperatureReading.equipment_id == eq["id"]))
    first.rejected_at = clock.now
    columns = {c.name: getattr(first, c.name) for c in TemperatureReading.__table__.columns if c.name != "id"}
    db.add(TemperatureReading(**columns | {"rejected_at": None, "recorded_at": clock.now - timedelta(days=30)}))
    db.commit()
    assert trend(client, steward, eq, "wash", days=7).json()["points"] == []
    assert len(trend(client, steward, eq, "wash", days=60).json()["points"]) == 1
    assert trend(client, steward, eq, "wash", days=0).status_code == 422 and trend(client, steward, eq, "wash", days=91).status_code == 422
    from app.api import monitoring
    monkeypatch.setattr(monitoring, "TREND_MAX_READINGS", 1)
    db.add(TemperatureReading(**columns | {"rejected_at": None, "recorded_at": clock.now - timedelta(days=20)}))
    db.commit()
    body = trend(client, steward, eq, "wash", days=60).json()
    assert len(body["points"]) == 1 and body["truncated"] is True


def test_trend_only_for_a_number_check_of_that_point_in_the_users_places(client, login, db):
    steward = login(STEWARD)
    eq = point(client, steward)
    assert client.get("/api/monitoring/trend", params={"equipment_id": eq["id"], "schedule_id": 99999}, headers=steward).status_code == 404
    rb = db.scalar(select(Equipment).where(Equipment.location_id == loc_id(db, "RB")))
    rb_check = db.scalar(select(EquipmentSchedule).where(EquipmentSchedule.equipment_id == rb.id))
    assert client.get("/api/monitoring/trend", params={"equipment_id": rb.id, "schedule_id": rb_check.id}, headers=login(SUP)).status_code == 403
    text = db.get(EquipmentSchedule, next(s["id"] for s in eq["schedules"] if s["stage"] == "wash"))
    text.value_type = "text"
    db.commit()
    assert client.get("/api/monitoring/trend", params={"equipment_id": eq["id"], "schedule_id": text.id}, headers=login(MGR)).status_code == 400
