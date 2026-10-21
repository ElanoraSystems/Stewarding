from sqlalchemy import select

from app.models import Notification

from .helpers import MGR, SUP, loc_id
from .test_absences import day_row, emp_id, record


def weekoff_shift(client, h):
    body = {"kind": "weekoff", "name": "Rest Day", "start_time": "09:00", "end_time": "17:00", "grace_minutes": 30}
    return client.post("/api/roster/shifts", json=body, headers=h)


def assign(client, h, db, shift, code="E004", loc="MK", weekdays=(0,), valid_from="2026-03-01", valid_to=None):
    return client.post("/api/roster/assignments", headers=h, json={
        "employee_id": emp_id(client, h, code), "shift_id": shift, "location_id": loc_id(db, loc),
        "weekdays": list(weekdays), "valid_from": valid_from, "valid_to": valid_to})


def test_week_off_shift_has_no_hours_and_is_listed_first(client, login):
    h = login(MGR)
    made = weekoff_shift(client, h).json()
    assert made["kind"] == "weekoff" and made["start_time"] == "00:00:00" and made["grace_minutes"] == 0
    assert client.get("/api/roster/shifts", headers=h).json()[0]["kind"] == "weekoff"


def clear_days(client, h, code="E004", weekdays=(0,)):
    for a in client.get(f"/api/roster/assignments?employee_id={emp_id(client, h, code)}", headers=h).json():
        if a["weekday"] in weekdays:
            client.delete(f"/api/roster/assignments/{a['id']}", headers=h)


def test_week_off_conflicts_with_a_working_shift_on_the_same_weekday(client, login, db, clock):
    h = login(MGR)
    off = weekoff_shift(client, h).json()["id"]
    assert assign(client, h, db, off, weekdays=(0,)).status_code == 409  # Sid already works Mondays
    clear_days(client, h, weekdays=(5,))
    assert assign(client, h, db, off, weekdays=(5,), valid_from="2026-03-09").status_code == 201


def test_a_shift_cannot_change_kind_once_assigned(client, login, db):
    h = login(MGR)
    shifts = client.get("/api/roster/shifts", headers=h).json()
    work = next(s for s in shifts if s["kind"] == "work")
    body = {**work, "kind": "weekoff"}
    assert client.put(f"/api/roster/shifts/{work['id']}", json=body, headers=h).status_code == 409


def test_week_off_day_is_flagged_not_scheduled_and_not_chased(client, login, db, clock):
    h = login(MGR)
    off = weekoff_shift(client, h).json()["id"]
    clear_days(client, h)
    assert assign(client, h, db, off, weekdays=(0,), valid_from="2026-03-09").status_code == 201
    clock.set(2026, 3, 9, 2, 5)  # the following Monday, after the working Monday ended
    assert day_row(client, h, db)["day_type"] == "week_off"
    k = client.get("/api/dashboard", headers=h).json()
    assert k["kpis"]["off_today"] >= 1 and k["kpis"]["scheduled_today"] == 2
    from app.services import alerts
    from app.db import SessionLocal
    clock.set(2026, 3, 9, 4, 0)
    with SessionLocal() as s:
        alerts.run_alerts(s, clock.now)
        assert not [n for n in s.scalars(select(Notification)) if "Sid Steward" in (n.body or "")]


def test_an_assignment_can_end_on_a_date_that_is_checked_listed_and_used_for_clashes(client, login, db, clock):
    h = login(MGR)
    off = weekoff_shift(client, h).json()["id"]
    work = next(s["id"] for s in client.get("/api/roster/shifts", headers=h).json() if s["kind"] == "work")
    clear_days(client, h, weekdays=(5,))
    assert assign(client, h, db, off, weekdays=(5,), valid_from="2026-03-09", valid_to="2026-03-01").status_code == 422
    assert assign(client, h, db, off, weekdays=(5,), valid_from="2026-03-09", valid_to="2026-03-31").status_code == 201
    saturday = [a for a in client.get(f"/api/roster/assignments?employee_id={emp_id(client, h)}", headers=h).json() if a["weekday"] == 5 and a["valid_from"] == "2026-03-09"]
    assert [a["valid_to"] for a in saturday] == ["2026-03-31"]
    assert assign(client, h, db, work, weekdays=(5,), valid_from="2026-03-20", valid_to="2026-04-10").status_code == 409
    assert assign(client, h, db, work, weekdays=(5,), valid_from="2026-04-01").status_code == 201
    assert assign(client, h, db, work, weekdays=(5,), valid_from="2026-03-01", valid_to="2026-03-08").status_code == 201
