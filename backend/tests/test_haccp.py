from datetime import timedelta

from app.services import haccp

from .helpers import MGR, STEWARD, loc_id


def point(client, h, db, template, loc="BQ"):
    return client.post("/api/equipment/from-template", json={"template": template, "location_id": loc_id(db, loc)}, headers=h).json()


def body(**over):
    return {"owner": "Head Chef", "team": "Head Chef, Stewarding Supervisor", "scope": "All kitchens", "products": "Cooked meals served hot", "review": "",
            "processes": [{"name": "Hot food", "steps": [{"name": "Receiving", "control": ""}, {"name": "Cooking", "control": ""}, {"name": "Cooling", "control": "CCP"}]},
                          {"name": "Salads", "steps": [{"name": "Washing", "control": ""}, {"name": "Cold holding", "control": "OPRP"}]}],
            "hazards": [{"step": "Cooking", "hazard": "Pathogens survive", "kind": "Biological", "significant": True, "control": "Core temperature checked"}], **over}


def test_the_plan_starts_with_a_set_of_hazards_and_a_review_sentence(client, login, db, clock):
    plan = client.get("/api/haccp/plan", headers=login(MGR)).json()
    assert not plan["saved"] and plan["version"] == 1 and len(plan["hazards"]) >= 8 and "reviewed at least once a year" in plan["review"]


def test_only_someone_who_sets_monitoring_up_can_save_it(client, login, db, clock):
    assert client.put("/api/haccp/plan", json=body(), headers=login(STEWARD)).status_code == 403
    saved = client.put("/api/haccp/plan", json=body(), headers=login(MGR)).json()
    assert saved["saved"] and saved["version"] == 1 and saved["owner"] == "Head Chef" and saved["revisions"][0]["note"] == "First version"
    assert len(saved["hazards"]) == 1 and saved["review"]  # an empty review text falls back to the standard sentence


def test_a_new_version_needs_a_note_and_keeps_the_history(client, login, db, clock):
    m = login(MGR)
    client.put("/api/haccp/plan", json=body(), headers=m)
    assert client.put("/api/haccp/plan", json=body(new_version=True), headers=m).status_code == 400
    second = client.put("/api/haccp/plan", json=body(new_version=True, note="Added fish and seafood"), headers=m).json()
    assert second["version"] == 2 and [r["version"] for r in second["revisions"]] == [1, 2]
    same = client.put("/api/haccp/plan", json=body(owner="Chef"), headers=m).json()  # an edit without a new version
    assert same["version"] == 2 and len(same["revisions"]) == 2 and same["owner"] == "Chef"


def test_the_control_points_come_from_the_monitoring_points_with_their_real_limits(client, login, db, clock):
    m = login(MGR)
    point(client, m, db, "cooking")
    point(client, m, db, "cooling")
    point(client, m, db, "chiller")
    doc = haccp.build_plan(db, clock.now, None, None, "Tester")
    rows = [r for g in doc["groups"] for r in g["rows"] if "limit" in r]
    levels = [r["level"] for r in rows]
    assert levels == sorted(levels, key=["CCP", "OPRP", "PRP"].index)  # critical points first
    cooking = next(r for r in rows if "core temperature" in r["check"].lower())
    assert "Fish and seafood 63" in cooking["limit"] and "Poultry 75" in cooking["limit"] and "maximum 120 °C" in cooking["limit"]
    assert any(r["level"] == "CCP" and r["when"].startswith("Within 2 h") for r in rows)  # a cooling stage
    assert any(r["point"].startswith("Banquet") or "Chiller" in r["point"] for r in rows)


def test_the_plan_downloads_as_a_pdf_and_the_download_is_audited(client, login, db, clock):
    m = login(MGR)
    point(client, m, db, "cooling")
    r = client.get("/api/haccp/plan/pdf", headers=m)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "haccp-plan-v1.pdf" in r.headers["content-disposition"]
    assert client.get("/api/audit?size=5", headers=m).status_code in (200, 403)


def test_there_is_a_flow_for_each_kind_of_food_with_every_step_from_the_supplier_on(client, login, db, clock):
    m = login(MGR)
    start = client.get("/api/haccp/plan", headers=m).json()["processes"]
    names = [p["name"] for p in start]
    assert names == ["Hot food", "Cold food and salads", "Stocks, soups and sauces", "Sushi and raw fish", "Cleaning, hygiene and waste (all areas)"]
    hot = {s["name"] for s in start[0]["steps"]}
    assert "Supplier approval and ordering" in hot and "Cooking" in hot and "Hot holding" in hot
    assert [s["name"] for p in start for s in p["steps"] if s["control"] == "CCP"] == ["Hot holding", "Cooling of leftovers", "Cooling", "Hot holding"]  # hot food, then stocks


def test_the_flows_are_saved_checked_and_drawn_one_chart_each(client, login, db, clock):
    m = login(MGR)
    saved = client.put("/api/haccp/plan", json=body(), headers=m).json()
    assert [p["name"] for p in saved["processes"]] == ["Hot food", "Salads"] and saved["processes"][1]["steps"][1]["control"] == "OPRP"
    twice = [{"name": "Hot food", "steps": []}, {"name": "hot  food", "steps": []}]
    assert client.put("/api/haccp/plan", json=body(processes=twice), headers=m).status_code == 422
    assert client.put("/api/haccp/plan", json=body(processes=[{"name": "Soup", "steps": [{"name": "Cooling", "control": "XYZ"}]}]), headers=m).status_code == 422
    doc = haccp.build_plan(db, clock.now, None, None, "Tester")
    charts = [g for g in doc["groups"] if g.get("flow") is not None]
    assert [g["title"] for g in charts] == ["2. Process flow: Hot food", "Process flow: Salads"]
    assert client.get("/api/haccp/plan/pdf", headers=m).content.startswith(b"%PDF")


def test_a_plan_saved_with_one_flow_becomes_one_process(client, login, db, clock):
    from app.models import HaccpPlan
    db.add(HaccpPlan(content={"owner": "Chef", "flow": [{"name": "Receiving", "control": ""}, {"name": "Cooling", "control": "CCP"}], "hazards": [], "revisions": []}, version=1))
    db.commit()
    plan = client.get("/api/haccp/plan", headers=login(MGR)).json()
    assert plan["processes"] == [{"name": "All food", "steps": [{"name": "Receiving", "control": ""}, {"name": "Cooling", "control": "CCP"}]}] and "flow" not in plan


def test_an_earlier_version_is_kept_exactly_and_can_be_opened_printed_and_restored(client, login, db, clock):
    m = login(MGR)
    client.put("/api/haccp/plan", json=body(owner="Head Chef"), headers=m)
    client.put("/api/haccp/plan", json=body(owner="Head Chef", scope="Edited in place"), headers=m)  # still version 1, nothing kept yet
    assert [v["version"] for v in client.get("/api/haccp/plan/versions", headers=m).json()] == [1]
    client.put("/api/haccp/plan", json=body(owner="New owner", new_version=True, note="Changed the owner"), headers=m)
    listed = client.get("/api/haccp/plan/versions", headers=m).json()
    assert [(v["version"], v["current"]) for v in listed] == [(2, True), (1, False)] and listed[0]["note"] == "Changed the owner" and listed[1]["note"] == "First version"
    old = client.get("/api/haccp/plan/versions/1", headers=m).json()
    assert old["owner"] == "Head Chef" and old["scope"] == "Edited in place"  # exactly as it stood when it was replaced
    assert client.get("/api/haccp/plan", headers=m).json()["owner"] == "New owner"
    assert client.get("/api/haccp/plan/pdf?version=1", headers=m).content.startswith(b"%PDF")
    assert client.get("/api/haccp/plan/pdf?version=9", headers=m).status_code == 404
    assert client.post("/api/haccp/plan/versions/2/restore", headers=m).status_code == 409  # already current
    assert client.post("/api/haccp/plan/versions/1/restore", headers=login(STEWARD)).status_code == 403
    back = client.post("/api/haccp/plan/versions/1/restore", headers=m).json()
    assert back["version"] == 3 and back["owner"] == "Head Chef" and back["revisions"][-1]["note"] == "Restored from version 1"
    assert [v["version"] for v in client.get("/api/haccp/plan/versions", headers=m).json()] == [3, 2, 1]  # nothing erased
    assert client.get("/api/haccp/plan/versions/2", headers=m).json()["owner"] == "New owner"
