import json

import pytest
from sqlalchemy import select

from app.models import AuditLog, Location

from .helpers import MGR, STEWARD, SUP, item_id, loc_id


@pytest.mark.parametrize("email", [SUP, STEWARD])
def test_settings_and_audit_are_manager_only(client, login, email):
    h = login(email)
    assert client.get("/api/settings", headers=h).status_code == 403
    assert client.put("/api/settings", json={"values": {"reminder.lead_minutes": 5}}, headers=h).status_code == 403
    assert client.post("/api/settings/locations", json={}, headers=h).status_code == 403
    assert client.get("/api/audit", headers=h).status_code == 403


def test_settings_have_defaults_validation_and_audit(client, login, db):
    m = login(MGR)
    current = client.get("/api/settings", headers=m).json()["settings"]
    assert current["reminder.lead_minutes"] == 30 and current["breakage.approval_qty"] == 5
    assert client.put("/api/settings", json={"values": {"nope": 1}}, headers=m).status_code == 400
    assert client.put("/api/settings", json={"values": {"reminder.lead_minutes": -5}}, headers=m).status_code == 400
    assert client.put("/api/settings", json={"values": {}}, headers=m).status_code == 422
    changed = client.put("/api/settings", json={"values": {"reminder.lead_minutes": 45}}, headers=m).json()["settings"]
    assert changed["reminder.lead_minutes"] == 45
    log = db.scalar(select(AuditLog).where(AuditLog.action == "settings.update"))
    assert log.before == {"reminder.lead_minutes": 30} and log.after == {"reminder.lead_minutes": 45}


def test_changing_a_threshold_changes_behaviour(client, login, db, clock):
    from .helpers import STEWARD as steward

    def report():
        return client.post("/api/breakage", headers=login(steward), json={
            "location_id": loc_id(db, "MK"), "item_id": item_id(db, "PL-001"), "qty": 3, "incident_type": "breakage"}).json()

    first = report()
    assert client.post(f"/api/breakage/{first['id']}/review", json={"qty": 3}, headers=login(SUP)).json()["status"] == "approved"
    client.put("/api/settings", json={"values": {"breakage.approval_qty": 2}}, headers=login(MGR))
    second = report()
    assert client.post(f"/api/breakage/{second['id']}/review", json={"qty": 3}, headers=login(SUP)).json()["status"] == "pending_approval"


def test_location_management_validates_timezone_and_never_exposes_the_pin(client, login, db):
    m = login(MGR)
    body = {"code": "ST1", "name": "Stewarding Station 1", "kind": "station", "timezone": "Asia/Kuwait", "pin": "4821"}
    assert client.post("/api/settings/locations", json={**body, "timezone": "Mars/Base"}, headers=m).status_code == 400
    assert client.post("/api/settings/locations", json={**body, "kind": "spaceship"}, headers=m).status_code == 422
    assert client.post("/api/settings/locations", json={**body, "pin": "12"}, headers=m).status_code == 422
    created = client.post("/api/settings/locations", json=body, headers=m)
    assert created.status_code == 201 and created.json()["pin_required"] is True
    assert "4821" not in created.text and "pin" not in {k for k in created.json() if k != "pin_required"}
    assert client.post("/api/settings/locations", json=body, headers=m).status_code == 409
    stored = db.scalar(select(Location).where(Location.code == "ST1"))
    assert stored.checkin_pin_hash and stored.checkin_pin_hash != "4821"
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "location.create"))
    assert "4821" not in json.dumps(audit.after) and audit.after["pin_set"] is True


def test_location_update_pin_flow_enforces_check_in(client, login, db, clock):
    m = login(MGR)
    mk = loc_id(db, "MK")
    assert client.put(f"/api/settings/locations/{mk}", json={"pin": "9090"}, headers=m).json()["pin_required"] is True
    h = login(STEWARD)
    assert client.post("/api/attendance/check-in", json={"location_id": mk}, headers=h).status_code == 403
    assert client.post("/api/attendance/check-in", json={"location_id": mk, "pin": "9090"}, headers=h).status_code == 201
    client.post("/api/attendance/check-out", json={"exception_reason": "Testing the PIN flow"}, headers=h)
    assert client.put(f"/api/settings/locations/{mk}", json={"clear_pin": True}, headers=m).json()["pin_required"] is False
    assert client.post("/api/attendance/check-in", json={"location_id": mk}, headers=h).status_code == 201
    assert client.put(f"/api/settings/locations/{mk}", json={"timezone": "Not/AZone"}, headers=m).status_code == 400
    assert client.put("/api/settings/locations/9999", json={"name": "Nope"}, headers=m).status_code == 404


def test_deactivated_location_cannot_be_checked_into(client, login, db, clock):
    mk = loc_id(db, "MK")
    client.put(f"/api/settings/locations/{mk}", json={"active": False}, headers=login(MGR))
    assert client.post("/api/attendance/check-in", json={"location_id": mk}, headers=login(STEWARD)).status_code == 400


def test_audit_log_records_sensitive_actions_with_user_and_values(client, login, db, clock):
    m = login(MGR)
    emps = {e["employee_code"]: e["id"] for e in client.get("/api/employees?size=50", headers=m).json()["items"]}
    client.put(f"/api/employees/{emps['E004']}", json={"job_title": "Senior Steward"}, headers=m)
    client.post(f"/api/employees/{emps['E005']}/deactivate", headers=m)
    client.put("/api/settings", json={"values": {"temp.retest_minutes": 20}}, headers=m)
    log = client.get("/api/audit?size=100", headers=m).json()
    actions = {i["action"] for i in log["items"]}
    assert {"login", "employee.update", "employee.deactivate", "settings.update"} <= actions
    update = next(i for i in log["items"] if i["action"] == "employee.update")
    assert update["user"] == "Maya Manager" and update["before"]["job_title"] == "Steward" and update["after"]["job_title"] == "Senior Steward"
    assert update["created_at"].endswith("Z")


def test_audit_filters_and_pagination(client, login, db, clock):
    m = login(MGR)
    emps = {e["employee_code"]: e["id"] for e in client.get("/api/employees?size=50", headers=m).json()["items"]}
    for title in ("A1", "B2", "C3"):
        client.put(f"/api/employees/{emps['E004']}", json={"job_title": f"Steward {title}"}, headers=m)
    page = client.get("/api/audit?action=employee&size=2&page=2", headers=m).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert client.get("/api/audit?entity=employee", headers=m).json()["total"] == 3
    manager_id = client.get("/api/auth/me", headers=m).json()["id"]
    assert client.get(f"/api/audit?user_id={manager_id}&action=employee", headers=m).json()["total"] == 3
    assert client.get("/api/audit?action=zzz", headers=m).json()["total"] == 0


def test_audit_entries_cannot_be_changed_through_the_api(client, login):
    m = login(MGR)
    assert client.put("/api/audit/1", json={}, headers=m).status_code in (404, 405)
    assert client.delete("/api/audit/1", headers=m).status_code in (404, 405)
    assert client.post("/api/audit", json={}, headers=m).status_code == 405


def test_critical_operations_are_audited(client, login, db, clock):
    m, sup, st = login(MGR), login(SUP), login(STEWARD)
    mk = loc_id(db, "MK")
    client.post("/api/attendance/check-in", json={"location_id": mk}, headers=st)
    client.post("/api/inventory/transactions", headers=m, json={
        "item_id": item_id(db, "PL-001"), "location_id": mk, "txn_type": "adjustment", "qty": -2, "reason": "Count correction"})
    client.post("/api/checklists/generate", json={"location_id": mk}, headers=m)
    task = client.get("/api/checklists/instances?size=200", headers=sup).json()["items"][0]
    client.post(f"/api/checklists/instances/{task['id']}/waive", json={"reason": "Equipment is out of order"}, headers=sup)
    actions = {a.action for a in db.scalars(select(AuditLog))}
    assert {"inventory.adjustment", "checklist.waive"} <= actions
