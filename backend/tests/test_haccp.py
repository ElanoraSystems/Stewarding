from app.services import haccp

from .helpers import MGR, STEWARD, loc_id


def point(client, h, db, template, loc="BQ"):
    return client.post("/api/equipment/from-template", json={"template": template, "location_id": loc_id(db, loc)}, headers=h).json()


def hz(**over):
    return {"hazard": "Pathogens survive", "kind": "Biological", "significant": True, "control": "Core temperature checked", "basis": "", **over}


def st(name="Cooking", **over):
    return {"name": name, "kind": "step", "control": "", "no_action": "", "hazards": [hz()], "no_hazard": "", **over}


def body(**over):
    return {"owner": "Head Chef", "team": "Head Chef, Stewarding Supervisor", "scope": "All kitchens", "products": "Cooked meals served hot", "review": "",
            "processes": [{"name": "Hot food", "steps": [st("Receiving"), st("Cooking"), st("Cooling", control="CCP")]},
                          {"name": "Salads", "steps": [st("Washing", hazards=[], no_hazard="Washed produce is sanitised in the next step")]}], **over}


def test_the_plan_starts_with_a_flow_for_each_kind_of_food_including_bakery_and_pastry(client, login, db, clock):
    plan = client.get("/api/haccp/plan", headers=login(MGR)).json()
    assert not plan["saved"] and plan["version"] == 1 and "reviewed at least once a year" in plan["review"]
    assert [p["name"] for p in plan["processes"]] == ["Hot food", "Cold food and salads", "Stocks, soups and sauces", "Sushi and raw fish", "Bakery (breads and doughs)",
                                                      "Pastry and desserts", "Cleaning, hygiene and waste (all areas)"]
    assert "CXC 52-2003" in next(p for p in plan["processes"] if p["name"] == "Sushi and raw fish")["references"]


def test_every_starter_step_is_analysed_every_decision_says_what_no_means_and_every_control_step_has_a_significant_hazard(client, login, db, clock):
    for p in client.get("/api/haccp/plan", headers=login(MGR)).json()["processes"]:
        assert len(p["steps"]) >= 7
        for s in p["steps"]:
            assert s["hazards"] or s["no_hazard"], (p["name"], s["name"])
            assert s["kind"] == "step" or s["no_action"], (p["name"], s["name"])
            assert not s["control"] or any(h["significant"] for h in s["hazards"]), (p["name"], s["name"])
        assert any(s["kind"] == "decision" for s in p["steps"]), p["name"]


def test_a_step_cannot_be_in_the_flow_without_being_analysed(client, login, db, clock):
    m = login(MGR)
    nothing = body(processes=[{"name": "Hot food", "steps": [st("Cooking", hazards=[])]}])
    r = client.put("/api/haccp/plan", json=nothing, headers=m)
    assert r.status_code == 422 and "needs at least one hazard" in r.text
    assert client.put("/api/haccp/plan", json=body(processes=[{"name": "Hot food", "steps": [st("Cooling", control="CCP", hazards=[hz(significant=False)])]}]), headers=m).status_code == 422
    no_answer = body(processes=[{"name": "Hot food", "steps": [st("Within the limit?", kind="decision")]}])
    assert client.put("/api/haccp/plan", json=no_answer, headers=m).status_code == 422
    fine = body(processes=[{"name": "Hot food", "steps": [st("Within the limit?", kind="decision", no_action="Keep cooking")]}])
    assert client.put("/api/haccp/plan", json=fine, headers=m).status_code == 200


def test_the_hazard_analysis_is_built_from_the_flow_with_the_same_step_numbers(client, login, db, clock):
    m = login(MGR)
    client.put("/api/haccp/plan", json=body(), headers=m)
    doc = haccp.build_plan(db, clock.now, None, None, "Tester")
    flows = [g for g in doc["groups"] if g.get("flow") is not None]
    analyses = [g for g in doc["groups"] if g["columns"][0] == ("step", "Step")]
    assert [g["title"] for g in flows] == ["2. Process flow: Hot food", "Process flow: Salads"]
    assert [g["title"] for g in analyses] == ["3. Hazard analysis: Hot food", "Hazard analysis: Salads"]
    for flow, analysis in zip(flows, analyses):
        assert [r["step"] for r in analysis["rows"] if r["step"]] == [f"{n}. {s['name']}" for n, s in enumerate(flow["flow"], 1)]  # the same steps, in the same order, numbered alike
    assert "No significant hazard: Washed produce" in analyses[1]["rows"][0]["hazard"]
    assert client.get("/api/haccp/plan/pdf", headers=m).content.startswith(b"%PDF")


def test_only_someone_who_sets_monitoring_up_can_save_it(client, login, db, clock):
    assert client.put("/api/haccp/plan", json=body(), headers=login(STEWARD)).status_code == 403
    saved = client.put("/api/haccp/plan", json=body(), headers=login(MGR)).json()
    assert saved["saved"] and saved["version"] == 1 and saved["owner"] == "Head Chef" and saved["revisions"][0]["note"] == "First version"
    assert saved["review"] and [p["name"] for p in saved["processes"]] == ["Hot food", "Salads"]  # an empty review text falls back to the standard sentence


def test_two_processes_cannot_share_a_name(client, login, db, clock):
    twice = [{"name": "Hot food", "steps": []}, {"name": "hot  food", "steps": []}]
    assert client.put("/api/haccp/plan", json=body(processes=twice), headers=login(MGR)).status_code == 422


def test_the_control_points_come_from_the_monitoring_points_with_their_real_limits(client, login, db, clock):
    m = login(MGR)
    for t in ("cooking", "cooling", "chiller"):
        point(client, m, db, t)
    doc = haccp.build_plan(db, clock.now, None, None, "Tester")
    rows = [r for g in doc["groups"] for r in g["rows"] if "limit" in r]
    assert [r["level"] for r in rows] == sorted((r["level"] for r in rows), key=["CCP", "OPRP", "PRP"].index)  # critical points first
    cooking = next(r for r in rows if "core temperature" in r["check"].lower())
    assert "Fish and seafood 63" in cooking["limit"] and "Poultry 75" in cooking["limit"] and "maximum 120 °C" in cooking["limit"]
    assert any(r["level"] == "CCP" and r["when"].startswith("Within 2 h") for r in rows)


def test_a_plan_saved_in_an_earlier_shape_keeps_its_hazards_on_the_matching_steps(client, login, db, clock):
    from app.models import HaccpPlan
    db.add(HaccpPlan(content={"owner": "Chef", "processes": [{"name": "Hot food", "steps": [{"name": "Receiving", "control": ""}, {"name": "Cooling", "control": "CCP"}]}],
                              "hazards": [{"step": "Cooling", "hazard": "Spores grow", "kind": "Biological", "significant": True, "control": "Cooling log", "process": ""},
                                          {"step": "Allergens", "hazard": "Cross-contact", "kind": "Allergen", "significant": True, "control": "Labels", "process": ""}], "revisions": []}, version=1))
    db.commit()
    plan = client.get("/api/haccp/plan", headers=login(MGR)).json()
    steps = {s["name"]: s for s in plan["processes"][0]["steps"]}
    assert steps["Cooling"]["hazards"][0]["hazard"] == "Spores grow" and steps["Receiving"]["hazards"] == []
    assert steps["Hazards not yet linked to a step"]["hazards"][0]["hazard"] == "Cross-contact"  # nothing written is lost, and it is plain to see
    assert "hazards" not in plan and "flow" not in plan


def test_an_earlier_version_is_kept_exactly_and_can_be_opened_printed_and_restored(client, login, db, clock):
    m = login(MGR)
    client.put("/api/haccp/plan", json=body(owner="Head Chef"), headers=m)
    client.put("/api/haccp/plan", json=body(owner="Head Chef", scope="Edited in place"), headers=m)  # still version 1, nothing kept yet
    assert [v["version"] for v in client.get("/api/haccp/plan/versions", headers=m).json()] == [1]
    client.put("/api/haccp/plan", json=body(owner="New owner", new_version=True, note="Changed the owner"), headers=m)
    listed = client.get("/api/haccp/plan/versions", headers=m).json()
    assert [(v["version"], v["current"]) for v in listed] == [(2, True), (1, False)] and listed[0]["note"] == "Changed the owner" and listed[1]["note"] == "First version"
    old = client.get("/api/haccp/plan/versions/1", headers=m).json()
    assert old["owner"] == "Head Chef" and old["scope"] == "Edited in place"
    assert client.get("/api/haccp/plan", headers=m).json()["owner"] == "New owner"
    assert client.get("/api/haccp/plan/pdf?version=1", headers=m).content.startswith(b"%PDF")
    assert client.get("/api/haccp/plan/pdf?version=9", headers=m).status_code == 404
    assert client.post("/api/haccp/plan/versions/2/restore", headers=m).status_code == 409
    assert client.post("/api/haccp/plan/versions/1/restore", headers=login(STEWARD)).status_code == 403
    back = client.post("/api/haccp/plan/versions/1/restore", headers=m).json()
    assert back["version"] == 3 and back["owner"] == "Head Chef" and back["revisions"][-1]["note"] == "Restored from version 1"
    assert [v["version"] for v in client.get("/api/haccp/plan/versions", headers=m).json()] == [3, 2, 1]
    assert client.get("/api/haccp/plan/versions/2", headers=m).json()["owner"] == "New owner"


def test_a_new_version_needs_a_note(client, login, db, clock):
    m = login(MGR)
    client.put("/api/haccp/plan", json=body(), headers=m)
    assert client.put("/api/haccp/plan", json=body(new_version=True), headers=m).status_code == 400


def test_the_plan_downloads_as_a_pdf(client, login, db, clock):
    m = login(MGR)
    point(client, m, db, "cooling")
    r = client.get("/api/haccp/plan/pdf", headers=m)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "haccp-plan-v1.pdf" in r.headers["content-disposition"]
