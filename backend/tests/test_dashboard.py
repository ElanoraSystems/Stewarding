from sqlalchemy import func, select

from app.models import InventoryBalance, InventoryItem

from .helpers import MGR, STEWARD, SUP, SUP_RB, item_id, loc_id


def dash(client, h, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/dashboard?{query}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def generate(client, login, db, code="MK"):
    client.post("/api/checklists/generate", json={"location_id": loc_id(db, code)}, headers=login(MGR))


def test_manager_kpis_cover_attendance_stock_and_low_stock(client, login, db, clock):
    k = dash(client, login(MGR))["kpis"]
    assert (k["scheduled_today"], k["checked_in"], k["not_checked_in"], k["on_duty"]) == (3, 0, 3, 0)
    client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "MK")}, headers=login(STEWARD))
    k = dash(client, login(MGR))["kpis"]
    assert (k["checked_in"], k["not_checked_in"], k["on_duty"]) == (1, 2, 1)
    qty = db.scalar(select(func.sum(InventoryBalance.qty)))
    assert k["inventory"]["qty"] == qty and k["inventory"]["value"] > 0
    low = db.execute(select(InventoryBalance, InventoryItem).join(InventoryItem, InventoryItem.id == InventoryBalance.item_id)
                     .where(InventoryBalance.qty < InventoryItem.min_level)).all()
    assert k["low_stock_items"] == len(low) == 3


def test_checklist_kpis_use_done_over_due_and_ignore_future_work(client, login, db, clock):
    generate(client, login, db)
    mk = loc_id(db, "MK")
    assert dash(client, login(MGR), location_id=mk)["kpis"]["daily_completion"] == {"numerator": 0, "denominator": 0, "percent": None}
    items = client.get("/api/checklists/instances?size=200", headers=login(STEWARD)).json()["items"]
    for t in [i for i in items if i["frequency"] != "weekly"][:2]:
        client.post(f"/api/checklists/instances/{t['id']}/complete", json={}, headers=login(STEWARD))
    clock.set(2026, 3, 2, 10, 0)  # past the 13:30 deadline, before the 17:00 weekly deadline
    k = dash(client, login(MGR), location_id=mk)["kpis"]
    assert k["daily_completion"] == {"numerator": 2, "denominator": 14, "percent": 14.3}
    assert k["weekly_completion"]["denominator"] == 0
    assert k["overdue_tasks"] == 12
    clock.set(2026, 3, 2, 14, 0)  # 18:00 Dubai, weekly tasks now overdue too
    assert dash(client, login(MGR), location_id=mk)["kpis"]["weekly_completion"]["denominator"] == 10


def test_temperature_kpis_and_equipment_attention(client, login, db, clock):
    clock.set(2026, 3, 2, 2, 45)
    h = login(STEWARD)
    eq = next(e for e in client.get("/api/temperature/equipment", headers=h).json() if e["code"] == "DW-MK-1")
    wash = next(s for s in eq["schedules"] if s["stage"] == "wash")
    for _ in range(3):
        client.post("/api/temperature/readings", headers=h, json={"equipment_id": eq["id"], "schedule_id": wash["id"], "temp_c": 20})
    k = dash(client, login(MGR), location_id=loc_id(db, "MK"))["kpis"]
    assert k["failed_temperature_checks"] == 3 and k["equipment_attention"] == 1
    assert k["temperature_checks"] == {"done": 1, "due": 4}


def test_breakage_kpis_and_monthly_trend(client, login, db, clock):
    client.post("/api/breakage", headers=login(STEWARD), json={"location_id": loc_id(db, "MK"), "item_id": item_id(db, "PL-001"),
                                                                "qty": 2, "incident_type": "breakage"})
    body = dash(client, login(MGR))
    assert body["kpis"]["breakage_today"] == 1 and body["kpis"]["breakage_month"] == 1
    trend = body["charts"]["breakage_trend"]
    assert len(trend) == 6 and trend[-1] == {"month": "2026-03", "incidents": 1, "qty": 2, "est_cost": 5.0}


def test_charts_follow_the_requested_range_and_movements(client, login, db, clock):
    client.post("/api/inventory/transactions", headers=login(SUP), json={
        "item_id": item_id(db, "PL-001"), "location_id": loc_id(db, "MK"), "txn_type": "receipt", "qty": 10})
    client.post("/api/inventory/transactions", headers=login(SUP), json={
        "item_id": item_id(db, "PL-001"), "location_id": loc_id(db, "MK"), "txn_type": "issue", "qty": 4})
    body = dash(client, login(MGR), date_from="2026-02-24", date_to="2026-03-02")
    assert [d["date"] for d in body["charts"]["task_trend"]][0] == "2026-02-24" and len(body["charts"]["task_trend"]) == 7
    today = next(d for d in body["charts"]["inventory_movement"] if d["date"] == "2026-03-02")
    assert today["in"] == 10 and today["out"] == 4  # opening stock is not a receipt
    assert body["filters"] == {"date_from": "2026-02-24", "date_to": "2026-03-02", "location_id": None}
    assert len(dash(client, login(MGR))["charts"]["task_trend"]) == 14


def test_filters_by_location_employee_and_equipment(client, login, db, clock):
    emps = {e["employee_code"]: e["id"] for e in client.get("/api/employees?size=50", headers=login(MGR)).json()["items"]}
    one = dash(client, login(MGR), location_id=loc_id(db, "RB"))
    assert one["kpis"]["scheduled_today"] == 1
    assert {r["location"] for r in one["charts"]["weekly_compliance"]} == {"Rooftop Bar"}
    emp = dash(client, login(MGR), employee_id=emps["E004"], date_from="2026-03-01", date_to="2026-03-02")
    assert [d["scheduled"] for d in emp["charts"]["attendance_trend"]] == [1, 1]
    eq = next(e for e in client.get("/api/equipment", headers=login(MGR)).json() if e["code"] == "DW-MK-1")
    filtered = dash(client, login(MGR), equipment_id=eq["id"])["charts"]["temperature_compliance"]
    assert [e["equipment"] for e in filtered if e["location"] == "Main Kitchen"] == ["Main Kitchen Dishwasher 1"]


def test_task_status_filter_adds_a_selected_series(client, login, db, clock):
    generate(client, login, db)
    clock.set(2026, 3, 2, 10, 0)
    trend = dash(client, login(MGR), task_status="overdue", location_id=loc_id(db, "MK"))["charts"]["task_trend"]
    assert trend[-1]["selected"] == 14 and trend[-1]["overdue"] == 14


def test_invalid_ranges_are_rejected(client, login, db):
    h = login(MGR)
    assert client.get("/api/dashboard?date_from=2026-03-05&date_to=2026-03-01", headers=h).status_code == 400
    assert client.get("/api/dashboard?date_from=2025-01-01&date_to=2026-03-01", headers=h).status_code == 400


def test_supervisor_dashboard_is_scoped_and_has_actionable_extras(client, login, db, clock):
    body = dash(client, login(SUP_RB))
    assert body["kpis"]["scheduled_today"] == 1
    assert set(body["supervisor"]) == {"pending", "staff_today", "stock_requests", "to_verify", "failed_readings_open"}
    assert all(s["name"] in ("Ravi Steward",) for s in body["supervisor"]["staff_today"])
    assert "supervisor" not in dash(client, login(MGR))
    assert client.get(f"/api/dashboard?location_id={loc_id(db, 'MK')}", headers=login(SUP_RB)).status_code == 403
    mk = dash(client, login(SUP))
    assert mk["kpis"]["scheduled_today"] == 2


def test_steward_dashboard_shows_only_my_shift(client, login, db, clock):
    generate(client, login, db)
    h = login(STEWARD)
    body = dash(client, h)
    assert body["role"] == "steward" and body["checked_in"] is False
    # 14 daily tasks plus the 8 Monday weekly tasks meant for stewards; the 2 supervisor-only tasks are hidden
    assert body["tasks"]["total"] == 22 and body["tasks"]["done"] == 0 and len(body["tasks"]["outstanding"]) == 20
    assert "kpis" not in body and body["unresolved_issues"] == 0
    client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "MK")}, headers=h)
    task = client.get("/api/checklists/instances?size=200", headers=h).json()["items"][0]
    client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=h)
    eq = next(e for e in client.get("/api/temperature/equipment", headers=h).json() if e["code"] == "DW-MK-1")
    wash = next(s for s in eq["schedules"] if s["stage"] == "wash")
    client.post("/api/temperature/readings", headers=h, json={"equipment_id": eq["id"], "schedule_id": wash["id"], "temp_c": 10})
    body = dash(client, h)
    assert body["checked_in"] is True and body["tasks"]["done"] == 1 and body["unresolved_issues"] == 1
    assert body["temperature_checks"]["due"] >= 1


def test_dashboard_requires_authentication(client):
    assert client.get("/api/dashboard").status_code == 401
