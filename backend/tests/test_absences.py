from sqlalchemy import select

from app.models import AuditLog

from .helpers import MGR, STEWARD, SUP, SUP_RB, loc_id


def emp_id(client, h, code="E004"):
    items = client.get("/api/employees?size=50", headers=h).json()["items"]
    return next(e["id"] for e in items if e["employee_code"] == code)


def record(client, h, db, day="2026-03-02", kind="absent", code="E004", loc="MK", **over):
    body = {"employee_id": emp_id(client, login_mgr(client), code), "location_id": loc_id(db, loc),
            "day": day, "absence_type": kind, **over}
    return client.post("/api/absences", json=body, headers=h)


def login_mgr(client):
    from .conftest import PASSWORD
    r = client.post("/api/auth/login", json={"email": MGR, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def day_row(client, h, db, name="Sid Steward"):
    rows = client.get(f"/api/roster/today?location_id={loc_id(db, 'MK')}", headers=h).json()
    return next(r for r in rows if r["name"] == name)


def test_absence_is_recorded_audited_and_shown_on_the_board(client, login, db, clock):
    h = login(SUP)
    r = record(client, h, db, kind="sick_leave", note="Doctor note")
    assert r.status_code == 201 and r.json()["status"] == "active"
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "absence.record"))
    row = day_row(client, h, db)
    assert row["day_type"] == "absence" and row["absence_type"] == "sick_leave"
    assert [a["id"] for a in client.get("/api/absences", headers=h).json()["items"]] == [r.json()["id"]]


def test_duplicate_day_is_refused_until_the_first_record_is_voided(client, login, db, clock):
    h = login(SUP)
    first = record(client, h, db).json()
    assert record(client, h, db, kind="annual_leave").status_code == 409
    assert client.post(f"/api/absences/{first['id']}/void", json={"reason": "no"}, headers=h).status_code == 422
    voided = client.post(f"/api/absences/{first['id']}/void", json={"reason": "Recorded in error"}, headers=h)
    assert voided.json()["status"] == "void"
    assert client.post(f"/api/absences/{first['id']}/void", json={"reason": "Recorded in error"}, headers=h).status_code == 409
    assert record(client, h, db, kind="annual_leave").status_code == 201


def test_an_employee_who_checked_in_cannot_be_marked_absent(client, login, db, clock):
    client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "MK")}, headers=login(STEWARD))
    r = record(client, login(SUP), db)
    assert r.status_code == 409 and "checked in" in r.json()["detail"]


def test_absence_permissions_scope_and_date_window(client, login, db, clock):
    assert record(client, login(STEWARD), db).status_code == 403
    assert record(client, login(SUP_RB), db).status_code == 403  # Main Kitchen is not theirs
    assert record(client, login(SUP), db, day="2026-01-01").status_code == 400
    assert record(client, login(SUP), db, code="E006").status_code == 400  # works at the rooftop bar only
    assert client.get("/api/absences", headers=login(STEWARD)).status_code == 403


def test_a_steward_sees_only_their_own_absences(client, login, db, clock):
    record(client, login(SUP), db)
    record(client, login(SUP), db, code="E005")
    mine = client.get("/api/absences/mine", headers=login(STEWARD)).json()
    assert len(mine) == 1 and mine[0]["employee_name"] == "Sid Steward"


def test_absence_and_leave_feed_the_dashboard_counts(client, login, db, clock):
    record(client, login(SUP), db)
    record(client, login(SUP), db, code="E005", loc="BQ", kind="annual_leave")
    k = client.get("/api/dashboard", headers=login(MGR)).json()
    today = k["charts"]["attendance_trend"][-1]
    assert today["absent"] == 1 and today["on_leave"] == 1
    assert today["scheduled"] == 2  # the absent steward stays scheduled, the one on leave does not
