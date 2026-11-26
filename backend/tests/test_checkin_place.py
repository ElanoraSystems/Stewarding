from datetime import date, datetime, time

from sqlalchemy import select

from app.models import AttendanceRecord, Employee, EmployeeLocation, Shift, ShiftAssignment

from .test_alerts import emails, notes, run
from .test_attendance import MGR, STEWARD, loc_id


def unattached(db):
    """A steward with no outlets assigned (the app treats that as free to work anywhere) and nothing on the roster."""
    emp = db.scalar(select(Employee).where(Employee.email == STEWARD))
    db.query(EmployeeLocation).filter(EmployeeLocation.employee_id == emp.id).delete()
    db.query(ShiftAssignment).filter(ShiftAssignment.employee_id == emp.id).delete()
    db.commit()
    return emp


def by_position(client, login):
    assert client.put("/api/settings", json={"values": {"attendance.by_location": 0}}, headers=login(MGR)).status_code == 200


def test_someone_not_rostered_with_several_places_to_pick_is_asked_not_guessed(client, login, db, clock):
    unattached(db)
    by_position(client, login)
    h = login(STEWARD)
    asked = client.post("/api/attendance/check-in", json={}, headers=h)
    assert asked.status_code == 422 and "Choose a location" in asked.json()["detail"]
    first = client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "BQ")}, headers=h)
    assert first.status_code == 201 and first.json()["location_id"] == loc_id(db, "BQ")
    client.post("/api/attendance/check-out", json={}, headers=h)
    clock.advance(days=1)
    again = client.post("/api/attendance/check-in", json={}, headers=h)  # still floating between places, so asked again, not sent to where they were last time
    assert again.status_code == 422
    assert client.get("/api/attendance/me/status", headers=h).json()["last_location_id"] == loc_id(db, "BQ")  # offered first in the list


def test_a_person_with_one_place_is_never_asked(client, login, db, clock):
    by_position(client, login)
    placed = client.post("/api/attendance/check-in", json={}, headers=login(STEWARD))
    assert placed.status_code == 201 and placed.json()["location_id"] == loc_id(db, "MK")


def test_a_check_in_with_no_shift_is_not_missed_until_the_longest_shift_and_its_grace_have_passed(client, login, db, clock):
    client.put("/api/settings", json={"values": {"attendance.missed_checkout_hours": 2}}, headers=login(MGR))  # the short limit that wrongly flagged night crews
    db.add(Shift(name="Long day", start_time=time(6, 0), end_time=time(18, 0), kind="work"))
    emp = db.scalar(select(Employee).where(Employee.email == STEWARD))
    db.add(AttendanceRecord(employee_id=emp.id, location_id=loc_id(db, "MK"), shift_id=None, local_date=date(2026, 3, 2),
                            check_in_at=datetime(2026, 3, 2, 14, 0), open_flag=1))  # 18:00 in Dubai
    db.commit()
    clock.set(2026, 3, 2, 21, 0)  # seven hours in: more than the two-hour setting, less than a 12 hour shift and its grace
    run(db, clock)
    assert notes(db, "missed_checkout") == []
    clock.set(2026, 3, 3, 5, 0)  # fifteen hours in: past the longest shift plus two hours
    run(db, clock)
    assert emails(db, notes(db, "missed_checkout")) >= {"manager@example.test", "steward.mk@example.test"}


def test_on_a_split_day_the_check_in_goes_to_the_shift_that_is_on_or_next(client, login, db, clock):
    emp = unattached(db)
    by_position(client, login)
    morning = Shift(name="Early", start_time=time(6, 0), end_time=time(10, 0), kind="work")
    evening = Shift(name="Late", start_time=time(16, 0), end_time=time(22, 0), kind="work")
    db.add_all([morning, evening])
    db.flush()
    for shift, code in ((morning, "MK"), (evening, "BQ")):  # the first place by name is not the evening one
        db.add(ShiftAssignment(employee_id=emp.id, shift_id=shift.id, location_id=loc_id(db, code), weekday=0, valid_from=date(2026, 1, 1)))  # a Monday
    db.commit()
    clock.set(2026, 3, 2, 12, 30)  # 16:30 in Dubai: the late shift is on
    got = client.post("/api/attendance/check-in", json={}, headers=login(STEWARD))
    assert got.status_code == 201 and got.json()["location_id"] == loc_id(db, "BQ")
