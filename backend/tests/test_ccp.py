from .helpers import MGR, STEWARD, SUP
from .test_alerts import notes, run
from .test_monitoring_general import check, point, record


def test_a_point_is_marked_as_a_ccp_and_only_a_manager_can_change_it(client, login, db):
    m = login(MGR)
    eq = point(client, m, db)
    assert eq["control_level"] == "prp"
    assert client.put(f"/api/equipment/{eq['id']}", json={"control_level": "ccp"}, headers=login(STEWARD)).status_code == 403
    assert client.put(f"/api/equipment/{eq['id']}", json={"control_level": "ccp"}, headers=m).json()["control_level"] == "ccp"
    assert client.put(f"/api/equipment/{eq['id']}", json={"name": "Renamed"}, headers=m).json()["control_level"] == "ccp"  # other edits keep it


def test_an_overdue_ccp_check_is_critical_and_says_so(client, login, db, clock):
    eq = next(e for e in client.get("/api/monitoring/equipment", headers=login(STEWARD)).json() if e["code"] == "DW-MK-1")
    run(db, clock)
    clock.advance(minutes=40)
    run(db, clock)
    plain = notes(db, "monitoring_overdue")
    assert plain and all(n.priority == "high" and n.title.startswith("Check overdue") for n in plain)
    assert client.put(f"/api/equipment/{eq['id']}", json={"control_level": "ccp"}, headers=login(MGR)).status_code == 200
    clock.advance(days=1)
    run(db, clock)
    run(db, clock)
    clock.advance(minutes=40)
    run(db, clock)
    ccp = [n for n in notes(db, "monitoring_overdue") if n.title.startswith("CCP check overdue")]
    assert ccp and all(n.priority == "critical" for n in ccp)


def test_a_failed_ccp_reading_is_labelled_and_the_approvals_list_and_record_carry_the_flag(client, login, db, clock):
    clock.set(2026, 3, 2, 4, 0)
    m = login(MGR)
    eq = point(client, m, db, code="SN-T-2")
    client.put(f"/api/equipment/{eq['id']}", json={"control_level": "ccp"}, headers=m)
    sched = check(client, m, eq).json()
    assert record(client, login(STEWARD), eq, sched, 50, corrective_action="Remixed the sanitiser").status_code == 201
    assert [n.title for n in notes(db, "monitoring_failed")][0].startswith("Failed CCP check")
    waiting = client.get("/api/approvals", headers=login(SUP)).json()["readings"]
    assert any(r["equipment"] == "Test point" and r["control"] == "ccp" for r in waiting)
    doc = client.get("/api/reports/records/monitoring?date_from=2026-03-02&date_to=2026-03-02", headers=m).json()
    group = next(g for g in doc["groups"] if "SN-T-2" in g["title"])
    assert group["title"].endswith(" - CCP") and ["Control level", "Critical control point (CCP)"] in [list(x) for x in group["meta"]]


def test_the_three_levels_are_labelled_differently_and_unknown_ones_are_refused(client, login, db, clock):
    m = login(MGR)
    eq = point(client, m, db, code="SN-T-3")
    assert client.put(f"/api/equipment/{eq['id']}", json={"control_level": "critical"}, headers=m).status_code == 422
    assert client.put(f"/api/equipment/{eq['id']}", json={"control_level": "oprp"}, headers=m).json()["control_level"] == "oprp"
    clock.set(2026, 3, 2, 4, 0)
    sched = check(client, m, eq).json()
    record(client, login(STEWARD), eq, sched, 50, corrective_action="Remixed")
    assert [n.title for n in notes(db, "monitoring_failed")][0].startswith("Failed OPRP check")
    assert [r["control"] for r in client.get("/api/approvals", headers=login(SUP)).json()["readings"]] == ["oprp"]
