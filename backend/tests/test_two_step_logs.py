from .helpers import MGR, STEWARD, loc_id


def make(client, h, db, template, loc="MK"):
    return client.post("/api/equipment/from-template", json={"template": template, "location_id": loc_id(db, loc)}, headers=h).json()


def checks(point, phase):
    return [c for c in point["schedules"] if c["phase"] == phase]


def start(client, h, point, item="Chicken thighs"):
    return client.post("/api/monitoring/readings/batch", headers=h, json={"equipment_id": point["id"], "readings": [
        {"schedule_id": c["id"], "value": 3, "reference": item} for c in checks(point, "start")]})


def finish(client, h, point, start_id, **over):
    readings = [{"schedule_id": c["id"], "value": 1 if c["value_type"] == "yes_no" else 3} for c in checks(point, "finish")]
    return client.post("/api/monitoring/readings/batch", headers=h, json={"equipment_id": point["id"], "start_reading_id": start_id, "readings": readings, **over})


def test_defrosting_and_cooling_are_two_step_and_cooking_is_not(client, login, db, clock):
    m = login(MGR)
    phases = {t: {c["phase"] for c in make(client, m, db, t)["schedules"]} for t in ("defrosting", "cooling", "cooking")}
    assert phases == {"defrosting": {"start", "finish"}, "cooling": {"start", "finish"}, "cooking": {None}}
    for template in ("defrosting", "cooling", "cooking"):
        point = make(client, m, db, template, "BQ")
        assert all(c["require_reference"] and c["reference_label"] == "Item or product name" for c in point["schedules"] if c["phase"] != "finish")


def test_a_time_in_stays_pending_until_the_time_out_is_recorded(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "defrosting")
    started = start(client, login(STEWARD), point).json()
    pending = client.get("/api/monitoring/pending", headers=m).json()
    assert [(p["equipment_id"], p["item"]) for p in pending] == [(point["id"], "Chicken thighs")]
    due = [d for d in client.get("/api/monitoring/due", headers=m).json() if d["equipment_id"] == point["id"]]
    assert {d["stage"] for d in due} == {"Time in"}

    assert finish(client, m, point, None).status_code == 400
    done = finish(client, m, point, started[0]["id"])
    assert done.status_code == 201 and {r["reference"] for r in done.json()} == {"Chicken thighs"}
    assert client.get("/api/monitoring/pending", headers=m).json() == []
    assert finish(client, m, point, started[0]["id"]).status_code == 409


def test_a_time_out_cannot_close_an_entry_of_another_point(client, login, db, clock):
    m = login(MGR)
    one, other = make(client, m, db, "defrosting"), make(client, m, db, "cooling")
    started = start(client, m, one).json()
    assert finish(client, m, other, started[0]["id"]).status_code == 400


def test_the_monitoring_record_lists_every_point_and_shows_pending_time_outs(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "defrosting")
    make(client, m, db, "chiller")
    start(client, m, point)
    doc = client.get("/api/reports/records/monitoring?date_from=2026-03-02&date_to=2026-03-02", headers=m).json()
    titles = [g["title"] for g in doc["groups"]]
    assert any("Chiller" in t for t in titles) and any("Defrosting" in t for t in titles)
    group = next(g for g in doc["groups"] if "Defrosting" in g["title"])
    assert [k for k, _ in group["columns"]][:3] == ["date", "time", "time_out"]
    assert group["rows"][0]["time_out"] == "Pending" and dict(group["totals"])["Waiting for time out"] == 1


def test_a_template_point_can_be_renamed(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "cooking")
    renamed = client.put(f"/api/equipment/{point['id']}", json={"name": "Hot kitchen cooking"}, headers=m)
    assert renamed.status_code == 200 and renamed.json()["name"] == "Hot kitchen cooking"


def test_date_and_time_fields_and_forms_without_a_schedule(client, login, db, clock):
    m = login(MGR)
    body = {"name": "Pest control visit", "kind": "Other", "location_ids": [loc_id(db, "MK")], "frequency": {"mode": "on_demand"},
            "fields": [{"title": "Visit date", "value_type": "date"}, {"title": "Arrival time", "value_type": "time"}]}
    made = client.post("/api/equipment/forms", json=body, headers=m)
    assert made.status_code == 201, made.text
    point = made.json()["points"][0]
    assert {c["timing"] for c in point["schedules"]} == {"manual"}
    assert [d for d in client.get("/api/monitoring/due", headers=m).json() if d["equipment_id"] == point["id"]] == []
    date_check, time_check = point["schedules"]
    ok = client.post("/api/monitoring/readings/batch", headers=m, json={"equipment_id": point["id"], "readings": [
        {"schedule_id": date_check["id"], "answer": "2026-03-02"}, {"schedule_id": time_check["id"], "answer": "14:30"}]})
    assert ok.status_code == 201 and [r["display"] for r in ok.json()] == ["2026-03-02", "14:30"]
    bad = client.post("/api/monitoring/readings", headers=m, json={"equipment_id": point["id"], "schedule_id": date_check["id"], "answer": "31/02/2026"})
    assert bad.status_code == 400


def test_an_existing_check_can_be_turned_into_a_time_in_and_keeps_its_step_when_edited_by_other_clients(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "chiller")
    sched = point["schedules"][0]
    body = {"stage": sched["stage"], "parameter": "Temperature", "unit": "C", "value_type": "number", "timing": "checkpoint",
            "min_value": 0, "max_value": 5, "phase": "start", "require_reference": True, "reference_label": "Item name"}
    edited = client.put(f"/api/equipment/schedules/{sched['id']}", json=body, headers=m).json()
    assert (edited["phase"], edited["reference_label"]) == ("start", "Item name")
    body.pop("phase"), body.pop("reference_label")
    assert client.put(f"/api/equipment/schedules/{sched['id']}", json=body, headers=m).json()["phase"] == "start"
