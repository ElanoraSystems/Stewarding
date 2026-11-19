from .test_checklists import STEWARD, SUP, find, generate, instances


def complete(client, h, task, **body):
    return client.post(f"/api/checklists/instances/{task['id']}/complete", json=body, headers=h)


def test_an_overdue_task_needs_a_reason_and_is_tagged_with_how_late_it_was(client, login, db, clock):
    generate(client, login, db)
    clock.set(2026, 3, 2, 10, 0)  # 14:00 in Dubai, half an hour after the 13:30 deadline
    steward, sup = login(STEWARD), login(SUP)
    task = find(client, steward, "Clean drains")
    assert task["effective_status"] == "overdue"
    refused = complete(client, steward, task)
    assert refused.status_code == 400 and "overdue by 30 min" in refused.json()["detail"]
    assert complete(client, steward, task, late_reason="  ok ").status_code == 400  # too short to be a reason
    done = complete(client, steward, task, late_reason="Delivery kept the team busy")
    assert done.status_code == 200
    assert done.json()["late_minutes"] == 30 and done.json()["late_reason"] == "Delivery kept the team busy"
    again = [i for i in instances(client, steward) if i["id"] == task["id"]][0]
    assert again["late_minutes"] == 30 and again["status"] == "pending_verification"  # the tag stays after it is completed
    waiting = client.get("/api/approvals", headers=sup).json()["tasks"]
    assert [(t["late_minutes"], t["late_reason"]) for t in waiting if t["id"] == task["id"]] == [(30, "Delivery kept the team busy")]


def test_a_task_done_on_time_or_within_the_grace_period_needs_no_reason(client, login, db, clock):
    generate(client, login, db)
    steward = login(STEWARD)
    early = find(client, steward, "Clean drains")
    done = complete(client, steward, early)
    assert done.status_code == 200 and done.json()["late_minutes"] is None and done.json()["late_reason"] is None
    clock.set(2026, 3, 2, 9, 40)  # 13:40 in Dubai: ten minutes late, still inside the 15 minute grace
    other = next(i for i in instances(client, steward) if i["status"] == "not_started" and i["id"] != early["id"] and i["frequency"] == "daily")
    ok = complete(client, steward, other)
    assert ok.status_code == 200 and ok.json()["late_minutes"] is None


def test_redoing_a_rejected_task_does_not_ask_for_a_late_reason_again(client, login, db, clock):
    generate(client, login, db)
    clock.set(2026, 3, 2, 10, 0)
    steward, sup = login(STEWARD), login(SUP)
    task = find(client, steward, "Clean drains")
    assert complete(client, steward, task, late_reason="Delivery kept the team busy").status_code == 200
    assert client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": False, "comment": "Photo missing"}, headers=sup).status_code == 200
    redo = complete(client, steward, task)
    assert redo.status_code == 200 and redo.json()["late_minutes"] == 30 and redo.json()["late_reason"] == "Delivery kept the team busy"  # the first lateness stays on record


def test_the_checklist_record_shows_who_was_late_and_why_and_hides_the_columns_when_nothing_was_late(client, login, db, clock):
    from .test_checklists import MGR, loc_id
    generate(client, login, db)
    steward = login(STEWARD)
    url = f"/api/reports/records/checklists?date_from=2026-03-02&date_to=2026-03-02&location_id={loc_id(db, 'MK')}"
    on_time = find(client, steward, "Clean drains")
    complete(client, steward, on_time)
    plain = client.get(url, headers=login(MGR)).json()
    assert all("late" not in [c[0] for c in g["columns"]] for g in plain["groups"])
    clock.set(2026, 3, 2, 10, 0)
    late = find(client, steward, "Separate and remove waste")
    assert complete(client, steward, late, late_reason="Waiting for the delivery").status_code == 200
    doc = client.get(url, headers=login(MGR)).json()
    group = next(g for g in doc["groups"] if "daily" in g["title"])
    assert ("late", "Late by") in [tuple(c) for c in group["columns"]]
    row = next(r for r in group["rows"] if r["task"] == "Separate and remove waste")
    assert row["late"] == "30 min" and row["late_reason"] == "Waiting for the delivery"
    assert next(r for r in group["rows"] if r["task"] == "Clean drains and remove debris")["late"] == ""
