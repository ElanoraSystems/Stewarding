from .test_checklists import MGR, STEWARD, SUP, find, generate
from .test_monitoring import mk_stage, record


def test_the_approvals_list_has_the_tasks_and_readings_waiting_for_the_person_who_approves_them(client, login, db, clock):
    generate(client, login, db)
    steward, sup, m = login(STEWARD), login(SUP), login(MGR)
    task = find(client, steward, "Clean drains")
    assert client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=steward).status_code == 200
    eq, wash = mk_stage(client, steward)
    reading = record(client, steward, eq, wash, 60.0).json()
    waiting = client.get("/api/approvals", headers=sup).json()
    assert [t["id"] for t in waiting["tasks"]] == [task["id"]] and waiting["tasks"][0]["description"].startswith("Clean drains") and waiting["tasks"][0]["done_by"]
    assert [r["id"] for r in waiting["readings"]] == [reading["id"]] and waiting["count"] == 2
    assert client.get("/api/approvals", headers=steward).json() == {"tasks": [], "readings": [], "count": 0}  # not an approver
    assert client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": True}, headers=sup).status_code == 200
    assert client.post("/api/monitoring/readings/review", json={"reading_ids": [reading["id"]]}, headers=sup).status_code == 200
    assert client.get("/api/approvals", headers=sup).json()["count"] == 0  # once decided they leave the list
    own = client.get("/api/approvals", headers=m).json()
    assert own["count"] == 0
