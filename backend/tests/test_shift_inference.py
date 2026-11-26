from datetime import time

from sqlalchemy import select

from app.models import AttendanceRecord, Employee, Shift, ShiftAssignment

from .test_attendance import MGR, STEWARD, loc_id


def unrostered(db):
    emp = db.scalar(select(Employee).where(Employee.email == STEWARD))
    db.query(ShiftAssignment).filter(ShiftAssignment.employee_id == emp.id).delete()
    db.commit()


def check_in(client, login, db):
    return client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "MK")}, headers=login(STEWARD))


def shift_named(db, name):
    return db.scalar(select(Shift.id).where(Shift.name == name))


def test_someone_nobody_rostered_is_put_on_the_shift_starting_nearest_their_check_in(client, login, db, clock):
    unrostered(db)
    clock.set(2026, 3, 2, 1, 30)  # 05:30 in Dubai, half an hour before the morning shift
    got = check_in(client, login, db)
    assert got.status_code == 201
    body = got.json()
    assert body["shift_id"] == shift_named(db, "Morning") and body["shift_inferred"] is True and body["late_minutes"] == 0


def test_a_guessed_shift_never_makes_someone_late_but_a_rostered_one_would(client, login, db, clock):
    unrostered(db)
    clock.set(2026, 3, 2, 2, 50)  # 06:50 in Dubai, 50 minutes after the morning start
    body = check_in(client, login, db).json()
    assert body["shift_inferred"] is True and body["late_minutes"] == 0


def test_no_shift_is_guessed_when_none_is_near_or_two_are_equally_near_or_the_setting_is_off(client, login, db, clock):
    unrostered(db)
    clock.set(2026, 3, 2, 6, 0)  # 10:00 in Dubai, four hours from either start
    far = check_in(client, login, db).json()
    assert far["shift_id"] is None and far["shift_inferred"] is False
    client.post("/api/attendance/check-out", json={}, headers=login(STEWARD))
    db.add(Shift(name="Between", start_time=time(14, 5), end_time=time(22, 5)))
    db.commit()
    clock.set(2026, 3, 2, 10, 0)  # 14:00: the evening shift is on the minute, the other five minutes later
    assert check_in(client, login, db).json()["shift_id"] is None
    client.post("/api/attendance/check-out", json={}, headers=login(STEWARD))
    assert client.put("/api/settings", json={"values": {"attendance.infer_shift_minutes": 0}}, headers=login(MGR)).status_code == 200
    clock.set(2026, 3, 3, 1, 30)
    assert check_in(client, login, db).json()["shift_id"] is None  # switched off


def test_a_rostered_person_keeps_their_own_shift_and_is_not_marked_inferred(client, login, db, clock):
    clock.set(2026, 3, 2, 2, 5)  # 06:05, rostered for the morning in the test data
    body = check_in(client, login, db).json()
    assert body["shift_id"] and body["shift_inferred"] is False


def test_a_manager_can_set_the_shift_and_lateness_follows(client, login, db, clock):
    unrostered(db)
    clock.set(2026, 3, 2, 2, 50)  # 06:50
    first = check_in(client, login, db).json()
    url = f"/api/attendance/{first['id']}/shift"
    assert client.post(url, json={"shift_id": shift_named(db, "Morning"), "reason": "Was on the early shift"}, headers=login(STEWARD)).status_code == 403
    done = client.post(url, json={"shift_id": shift_named(db, "Morning"), "reason": "Was on the early shift"}, headers=login(MGR)).json()
    assert done["shift_inferred"] is False and done["late_minutes"] == 50  # now judged against the shift they were really on
    week_off = db.scalar(select(Shift.id).where(Shift.kind == "weekoff"))
    assert client.post(url, json={"shift_id": week_off, "reason": "Not a working shift"}, headers=login(MGR)).status_code == 400
    assert client.post(url, json={"shift_id": None, "reason": "No shift that day"}, headers=login(MGR)).json()["late_minutes"] == 0
    assert db.scalar(select(AttendanceRecord).where(AttendanceRecord.id == first["id"])).shift_id is None
