from sqlalchemy import select

from app.models import User

from .test_checklists import MGR, STEWARD, SUP, find, generate
from .test_monitoring import mk_stage, record


def uid(db, email):
    return db.scalar(select(User.id).where(User.email == email))


def template_of(client, h, task):
    for t in client.get("/api/checklists/templates", headers=h).json():
        if any(k["id"] == task["task_id"] for k in t["tasks"]):
            return t["id"]
    raise AssertionError("template not found")


def test_only_people_who_can_approve_are_offered_and_accepted(client, login, db):
    generate(client, login, db)
    steward, sup, m = login(STEWARD), login(SUP), login(MGR)
    offered = {c["id"] for c in client.get("/api/approvals/approvers?kind=checklists", headers=m).json()}
    assert uid(db, SUP) in offered and uid(db, MGR) in offered and uid(db, STEWARD) not in offered
    assert client.get("/api/approvals/approvers?kind=nonsense", headers=m).status_code == 400
    task = find(client, steward, "Clean drains")
    tid = template_of(client, m, task)
    assert client.put(f"/api/checklists/templates/{tid}", json={"approvers": [uid(db, STEWARD)]}, headers=m).status_code == 400  # a steward cannot approve
    saved = client.put(f"/api/checklists/templates/{tid}", json={"approvers": [uid(db, SUP), uid(db, SUP), 999999][:2]}, headers=m)
    assert saved.status_code == 200 and saved.json()["approvers"] == [uid(db, SUP)] and saved.json()["approver_names"]
    assert client.put(f"/api/checklists/templates/{tid}", json={"approvers": []}, headers=m).json()["approvers"] is None  # empty means everyone again


def test_a_checklist_is_approved_only_by_the_people_named_on_it_and_a_manager_can_step_in(client, login, db, clock):
    generate(client, login, db)
    steward, sup, m = login(STEWARD), login(SUP), login(MGR)
    task = find(client, steward, "Clean drains")
    tid = template_of(client, m, task)
    client.put(f"/api/checklists/templates/{tid}", json={"approvers": [uid(db, MGR)]}, headers=m)  # the supervisor is not one of them
    assert client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=steward).status_code == 200
    assert client.get("/api/approvals", headers=sup).json()["tasks"] == []  # not on their list
    assert [t["id"] for t in client.get("/api/approvals", headers=m).json()["tasks"]] == [task["id"]]
    refused = client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": True}, headers=sup)
    assert refused.status_code == 403 and "chosen" in refused.json()["detail"]
    assert client.post("/api/checklists/instances/verify-many", json={"instance_ids": [task["id"]]}, headers=sup).json() == {"approved": 0, "skipped": 1}
    client.put(f"/api/checklists/templates/{tid}", json={"approvers": [uid(db, SUP), uid(db, MGR)]}, headers=m)  # two people, either one
    assert [t["id"] for t in client.get("/api/approvals", headers=sup).json()["tasks"]] == [task["id"]]
    assert client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": True}, headers=sup).status_code == 200
    assert client.get("/api/approvals", headers=m).json()["tasks"] == []  # the first to act decided it


def test_a_manager_can_approve_even_when_others_are_named(client, login, db, clock):
    generate(client, login, db)
    steward, sup, m = login(STEWARD), login(SUP), login(MGR)
    task = find(client, steward, "Clean drains")
    tid = template_of(client, m, task)
    client.put(f"/api/checklists/templates/{tid}", json={"approvers": [uid(db, SUP)]}, headers=m)
    client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=steward)
    assert client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": True}, headers=m).status_code == 200


def test_a_monitoring_log_is_reviewed_only_by_the_people_named_on_it(client, login, db, clock):
    generate(client, login, db)
    steward, sup, m = login(STEWARD), login(SUP), login(MGR)
    equipment, stage = mk_stage(client, steward)
    eq = equipment["id"]
    reading = record(client, steward, equipment, stage, 60.0).json()
    assert client.get("/api/approvals/approvers?kind=monitoring", headers=m).status_code == 200
    saved = client.put(f"/api/equipment/{eq}", json={"approvers": [uid(db, MGR)]}, headers=m)
    assert saved.status_code == 200 and saved.json()["approvers"] == [uid(db, MGR)] and saved.json()["approver_names"]
    assert client.put(f"/api/equipment/{eq}", json={"approvers": [uid(db, STEWARD)]}, headers=m).status_code == 400
    assert client.get("/api/approvals", headers=sup).json()["readings"] == []
    assert client.post(f"/api/monitoring/readings/{reading['id']}/review", json={}, headers=sup).status_code == 403
    assert client.post("/api/monitoring/readings/review", json={"reading_ids": [reading["id"]]}, headers=sup).json() == {"reviewed": 0, "skipped": 1}
    assert client.post("/api/monitoring/readings/reject", json={"reading_ids": [reading["id"]], "reason": "Wrong probe used"}, headers=sup).json() == {"rejected": 0, "skipped": 1}
    client.put(f"/api/equipment/{eq}", json={"approvers": [uid(db, SUP), uid(db, MGR)]}, headers=m)
    assert [r["id"] for r in client.get("/api/approvals", headers=sup).json()["readings"]] == [reading["id"]]
    assert client.post(f"/api/monitoring/readings/{reading['id']}/review", json={}, headers=sup).status_code == 200
