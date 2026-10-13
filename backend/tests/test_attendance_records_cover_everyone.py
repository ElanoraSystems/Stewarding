from .helpers import MGR, SUP, loc_id
from .test_absences import emp_id, login_mgr
from .test_attendance import check_in

URL = "/api/reports/records"


def rows_of(doc, name):
    return [r for g in doc["groups"] for r in g["rows"] if r.get("employee") == name]


def test_punches_and_manual_entries_of_an_unrostered_employee_reach_the_records(client, login, db, clock):
    mgr, sup = login(MGR), login(SUP)
    assert check_in(client, sup, db).status_code == 201
    assert client.post("/api/attendance/check-out", json={"location_id": loc_id(db, "MK")}, headers=sup).status_code in (200, 201)
    manual = client.post("/api/attendance/manual", headers=mgr, json={
        "employee_id": emp_id(client, login_mgr(client), "E002"), "location_id": loc_id(db, "MK"), "day": "2026-02-27",
        "check_in_time": "07:00:00", "check_out_time": "15:00:00", "reason": "Forgot to punch, confirmed"})
    assert manual.status_code == 201, manual.text

    doc = client.get(f"{URL}/attendance?date_from=2026-02-27&date_to=2026-03-02", headers=mgr).json()
    sam = rows_of(doc, "Sam Supervisor")
    assert {r["date"] for r in sam} == {"27 Feb 2026", "02 Mar 2026"}
    assert all(r["check_in"] for r in sam) and next(r for r in sam if r["date"] == "27 Feb 2026")["check_out"] == "15:00"
    assert next(r for r in sam if r["date"] == "27 Feb 2026")["note"].startswith("Manual entry")
    main = next(g for g in doc["groups"] if "Main Kitchen" in g["title"])
    present_rows = sum(1 for r in main["rows"] if r["status"] in ("Present", "Late", "Unscheduled", "On duty"))
    assert dict(main["totals"])["Present"] == present_rows

    sheet = client.get(f"{URL}/attendance_sheet?date_from=2026-02-27&date_to=2026-03-02", headers=mgr).json()
    assert any("Sam Supervisor" in g["title"] and len(g["rows"]) >= 2 for g in sheet["groups"])
