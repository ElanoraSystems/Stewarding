import pytest
from sqlalchemy import select

from app.models import AuditLog, Location

from .conftest import PASSWORD

MGR = "manager@example.test"


def loc_id(db, code):
    return db.scalar(select(Location.id).where(Location.code == code))


def payload(db, **over):
    base = {"employee_code": "E100", "full_name": "Nina New", "job_title": "Steward", "email": "nina@example.com",
            "password": "a-long-test-password", "role": "steward", "phone": "555-0100",
            "emergency_contact": "Pat, 555-0101", "location_ids": [loc_id(db, "MK")]}
    return {**base, **over}


def by_code(client, headers):
    items = client.get("/api/employees?size=100", headers=headers).json()["items"]
    return {e["employee_code"]: e for e in items}


def test_manager_creates_employee_who_can_sign_in(client, login, db):
    r = client.post("/api/employees", json=payload(db), headers=login(MGR))
    assert r.status_code == 201
    signin = client.post("/api/auth/login", json={"email": "nina@example.com", "password": "a-long-test-password"})
    assert signin.status_code == 200


@pytest.mark.parametrize("email", ["sup.mk@example.test", "steward.mk@example.test"])
def test_only_manager_can_create_or_edit(client, login, db, email):
    h = login(email)
    assert client.post("/api/employees", json=payload(db), headers=h).status_code == 403
    assert client.put("/api/employees/1", json={"job_title": "x1"}, headers=h).status_code == 403
    assert client.post("/api/employees/1/deactivate", headers=h).status_code == 403


def test_steward_cannot_list_employees(client, login):
    assert client.get("/api/employees", headers=login("steward.mk@example.test")).status_code == 403


def test_supervisor_is_scoped_and_sees_no_private_fields(client, login, db):
    rb = loc_id(db, "RB")
    body = client.get("/api/employees?size=100", headers=login("sup.rb@example.test")).json()
    assert body["items"] and all(rb in e["location_ids"] for e in body["items"])
    assert all("phone" not in e and "emergency_contact" not in e for e in body["items"])
    manager_view = client.get("/api/employees", headers=login(MGR)).json()["items"][0]
    assert "phone" in manager_view and "emergency_contact" in manager_view


def test_supervisor_cannot_open_employee_at_other_location(client, login):
    emps = by_code(client, login(MGR))
    r = client.get(f"/api/employees/{emps['E004']['id']}", headers=login("sup.rb@example.test"))
    assert r.status_code == 403


def test_duplicate_code_or_email_conflicts(client, login, db):
    h = login(MGR)
    assert client.post("/api/employees", json=payload(db), headers=h).status_code == 201
    assert client.post("/api/employees", json=payload(db, email="other@example.com"), headers=h).status_code == 409
    assert client.post("/api/employees", json=payload(db, employee_code="E101"), headers=h).status_code == 409


def test_weak_password_and_unknown_location_rejected(client, login, db):
    h = login(MGR)
    assert client.post("/api/employees", json=payload(db, password="short"), headers=h).status_code == 422
    assert client.post("/api/employees", json=payload(db, location_ids=[9999]), headers=h).status_code == 400


def test_deactivate_blocks_sign_in_and_is_audited(client, login, db):
    emps = by_code(client, login(MGR))
    steward = emps["E004"]
    h = login(MGR)
    assert client.post(f"/api/employees/{steward['id']}/deactivate", headers=h).status_code == 200
    r = client.post("/api/auth/login", json={"email": "steward.mk@example.test", "password": PASSWORD})
    assert r.status_code == 401
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "employee.deactivate"))
    assert client.post(f"/api/employees/{steward['id']}/activate", headers=h).status_code == 200
    assert client.post("/api/auth/login", json={"email": "steward.mk@example.test", "password": PASSWORD}).status_code == 200


def test_manager_cannot_deactivate_self(client, login):
    h = login(MGR)
    me_id = by_code(client, h)["E001"]["id"]
    assert client.post(f"/api/employees/{me_id}/deactivate", headers=h).status_code == 400


def test_assignment_change_is_recorded(client, login, db):
    h = login(MGR)
    steward = by_code(client, h)["E004"]
    r = client.put(f"/api/employees/{steward['id']}", json={"location_ids": [loc_id(db, "MK"), loc_id(db, "BQ")]},
                   headers=h)
    assert r.status_code == 200 and len(r.json()["location_ids"]) == 2
    log = db.scalar(select(AuditLog).where(AuditLog.action == "employee.assignment_change"))
    assert log and len(log.before["location_ids"]) == 1 and len(log.after["location_ids"]) == 2


def test_search_sort_and_pagination(client, login):
    h = login(MGR)
    page2 = client.get("/api/employees?size=2&page=2&sort=full_name", headers=h).json()
    assert page2["total"] == 6 and len(page2["items"]) == 2
    found = client.get("/api/employees?search=Sid", headers=h).json()["items"]
    assert [e["employee_code"] for e in found] == ["E004"]
    desc = client.get("/api/employees?sort=employee_code&dir=desc", headers=h).json()["items"]
    assert desc[0]["employee_code"] == "E006"
