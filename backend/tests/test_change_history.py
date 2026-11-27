from .helpers import MGR, STEWARD, SUP, loc_id
from .test_approvals import complete
from .test_checklists import find, generate, instances


def edit_task(client, h, task_id, **over):
    current = next(t for tpl in client.get("/api/checklists/templates", headers=h).json() for t in tpl["tasks"] if t["id"] == task_id)
    body = {k: current[k] for k in ("description", "instructions", "shift_id", "assigned_role", "assigned_employee_id", "weekdays", "priority", "requires_photo",
                                    "requires_reading", "requires_verification", "mandatory_for_checkout", "escalation_minutes", "active_from", "active_to", "active")}
    body["scheduled_time"], body["deadline_time"] = current["scheduled_time"], current["deadline_time"]
    return client.put(f"/api/checklists/tasks/{task_id}", json={**body, **over}, headers=h)


def test_a_completed_task_keeps_the_wording_it_was_ticked_under(client, login, db, clock):
    generate(client, login, db)
    steward, m = login(STEWARD), login(MGR)
    done, waiting = find(client, steward, "Clean drains"), find(client, steward, "Clean dishwasher filters")
    assert complete(client, steward, done).status_code == 200
    assert edit_task(client, m, done["task_id"], description="Clean and flush floor drains").status_code == 200
    assert edit_task(client, m, waiting["task_id"], description="Wash, rinse and sanitise surfaces").status_code == 200
    after = {i["id"]: i for i in instances(client, m)}
    assert after[done["id"]]["description"] == "Clean drains and remove debris"  # as it was when ticked
    assert after[waiting["id"]]["description"] == "Wash, rinse and sanitise surfaces"  # not done yet: the current wording


def test_the_change_history_of_a_checklist_shows_who_changed_what_from_and_to(client, login, db, clock):
    generate(client, login, db)
    m = login(MGR)
    task = find(client, m, "Clean drains")
    edit_task(client, m, task["task_id"], description="Clean and flush floor drains", priority="high")
    template = next(t for t in client.get("/api/checklists/templates", headers=m).json() if any(k["id"] == task["task_id"] for k in t["tasks"]))
    rows = client.get(f"/api/checklists/templates/{template['id']}/history", headers=m).json()
    change = next(r for r in rows if r["what"] == "Changed a task")
    assert change["by"] and change["subject"] == "Clean and flush floor drains"
    fields = {c["field"]: (c["from"], c["to"]) for c in change["changes"]}
    assert fields["Description"] == ("Clean drains and remove debris", "Clean and flush floor drains") and fields["Priority"][1] == "high"
    assert "Id" not in fields and "Template id" not in fields
    assert client.get(f"/api/checklists/templates/{template['id']}/history", headers=login(STEWARD)).status_code == 403


def test_the_change_history_of_a_monitoring_point_covers_its_checks(client, login, db, clock):
    m = login(MGR)
    point = client.post("/api/equipment/from-template", json={"template": "chiller", "location_id": loc_id(db, "BQ")}, headers=m).json()
    check = point["schedules"][0]
    body = {k: check[k] for k in ("stage", "parameter", "unit", "value_type", "source", "timing", "min_value", "max_value")}
    body["time_of_day"] = check["time_of_day"]
    assert client.put(f"/api/equipment/schedules/{check['id']}", json={**body, "max_value": 4}, headers=m).status_code == 200
    rows = client.get(f"/api/equipment/{point['id']}/history", headers=m).json()
    update = next(r for r in rows if r["what"] == "Changed a check")
    assert update["subject"] == check["stage"] and any(c["field"] == "Max value" and c["to"] in ("4", "4.0", "4.00") for c in update["changes"])
    assert any(r["what"] == "Created the monitoring point" for r in rows)
    assert client.get(f"/api/equipment/{point['id']}/history", headers=login(SUP)).status_code in (200, 403)  # allowed only for those who set monitoring up
    assert client.get(f"/api/equipment/{point['id']}/history", headers=login(STEWARD)).status_code == 403
