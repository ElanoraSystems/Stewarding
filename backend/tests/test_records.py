import io

from openpyxl import load_workbook
from sqlalchemy import select

from app.models import AuditLog

from .helpers import loc_id
from .test_approvals import SUP_RB, complete, verify
from .test_checklists import MGR, STEWARD, SUP, find, generate
from .test_monitoring import mk_stage, record

URL = "/api/reports/records"


def monitoring(client, h, **params):
    query = "&".join(f"{k}={v}" for k, v in {"date_from": "2026-03-02", "date_to": "2026-03-02", **params}.items())
    return client.get(f"{URL}/monitoring?{query}", headers=h)


def seed_readings(client, login):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    _, rinse = mk_stage(client, steward, "final_rinse")
    good = record(client, steward, eq, wash, 60).json()
    record(client, steward, eq, rinse, 70, corrective_action="Descaled the heater").json()
    client.post("/api/monitoring/readings/review", json={"reading_ids": [good["id"]]}, headers=sup)


def test_monitoring_record_lists_who_what_when_and_the_corrective_action(client, login, db, clock):
    seed_readings(client, login)
    doc = monitoring(client, login(MGR), location_id=loc_id(db, "MK")).json()
    assert doc["title"] == "Monitoring Record" and doc["locations"] == ["Main Kitchen"] and doc["prepared_by"] == "Maya Manager"
    group = next(g for g in doc["groups"] if "DW-MK-1" in g["title"])
    assert group["title"] == "Main Kitchen - Main Kitchen Dishwasher 1 (DW-MK-1)"
    assert dict(group["meta"])["Type"] == "Dishwasher"
    wash, rinse = group["rows"]
    assert (wash["check"], wash["value"], wash["limits"], wash["result"]) == ("Wash", "60 °C", "55 to 65 °C", "Pass")
    assert wash["date"] == "02 Mar 2026" and wash["time"] == "06:05" and wash["recorded_by"] == "Sid Steward"
    assert wash["approved_by"].startswith("Sam Supervisor 02 Mar 2026 06:05")
    assert rinse["result"] == "FAIL" and rinse["approved_by"] == "Awaiting approval"
    assert "Descaled the heater" in rinse["corrective_action"] and "Sid Steward" in rinse["corrective_action"]
    totals = dict(group["totals"])
    assert totals == {"Checks recorded": 2, "Passed": 1, "Failed": 1, "Awaiting approval": 1}


def test_records_export_as_pdf_excel_and_csv_and_are_audited(client, login, db, clock):
    seed_readings(client, login)
    h = login(MGR)
    pdf = client.get(f"{URL}/monitoring/export?fmt=pdf&date_from=2026-03-02&date_to=2026-03-02", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and "attachment" in pdf.headers["content-disposition"]
    xlsx = client.get(f"{URL}/monitoring/export?fmt=xlsx&date_from=2026-03-02&date_to=2026-03-02", headers=h)
    sheet = load_workbook(io.BytesIO(xlsx.content)).worksheets[0]
    cells = [c.value for row in sheet.iter_rows() for c in row if c.value]
    assert "Monitoring Record" in cells and "Descaled the heater (Sid Steward, retest due)" in cells
    csv = client.get(f"{URL}/monitoring/export?fmt=csv&date_from=2026-03-02&date_to=2026-03-02", headers=h).content.decode("utf-8-sig")
    assert "Monitoring Record" in csv and "Recorded by" in csv and "Sid Steward" in csv
    assert len(db.scalars(select(AuditLog).where(AuditLog.action == "report.export", AuditLog.entity == "record")).all()) == 3


def test_empty_period_still_produces_a_document(client, login, db, clock):
    h = login(MGR)
    doc = monitoring(client, h, date_from="2026-01-01", date_to="2026-01-01").json()
    assert doc["groups"] == []
    pdf = client.get(f"{URL}/monitoring/export?fmt=pdf&date_from=2026-01-01&date_to=2026-01-01", headers=h)
    assert pdf.content.startswith(b"%PDF")


def test_record_scope_validation_and_permissions(client, login, db, clock):
    seed_readings(client, login)
    assert monitoring(client, login(STEWARD)).status_code == 403
    assert client.get(f"{URL}/monitoring/export", headers=login(STEWARD)).status_code == 403
    assert monitoring(client, login(SUP_RB), location_id=loc_id(db, "MK")).status_code == 403
    assert monitoring(client, login(SUP_RB)).json()["groups"] == []  # the rooftop bar has no readings
    mine = monitoring(client, login(SUP)).json()
    assert {g["meta"][0][1] for g in mine["groups"]} == {"Main Kitchen"}
    assert monitoring(client, login(MGR), date_from="2026-03-05", date_to="2026-03-01").status_code == 400
    assert monitoring(client, login(MGR), date_from="2024-01-01", date_to="2026-03-01").status_code == 400
    assert client.get(f"{URL}/nonsense", headers=login(MGR)).status_code == 404
    assert client.get(f"{URL}/monitoring", headers=None).status_code == 401


def test_a_month_record_filters_by_monitoring_point(client, login, db, clock):
    seed_readings(client, login)
    h = login(MGR)
    eq, _ = mk_stage(client, h)
    other, _ = mk_stage(client, h, "wash", "GW-MK-1")
    doc = monitoring(client, h, date_from="2026-03-01", date_to="2026-03-31", equipment_id=eq["id"]).json()
    assert len(doc["groups"]) == 1 and doc["period"]["label"] == "01 Mar 2026 to 31 Mar 2026"
    assert monitoring(client, h, equipment_id=other["id"]).json()["groups"] == []


def test_checklist_record_shows_completion_and_approval(client, login, db, clock):
    generate(client, login, db)
    steward = login(STEWARD)
    done = find(client, steward, "Clean drains")
    complete(client, steward, done)
    verify(client, login(SUP), done)
    complete(client, steward, find(client, steward, "Separate and remove waste"))
    doc = client.get(f"{URL}/checklists?date_from=2026-03-02&date_to=2026-03-02&location_id={loc_id(db, 'MK')}", headers=login(MGR)).json()
    group = next(g for g in doc["groups"] if "daily" in g["title"])
    row = next(r for r in group["rows"] if r["task"] == "Clean drains and remove debris")
    assert (row["status"], row["completed_by"], row["verified_by"]) == ("verified", "Sid Steward", "Sam Supervisor")
    waiting = next(r for r in group["rows"] if r["task"] == "Separate and remove waste")
    assert waiting["status"] == "pending verification" and waiting["verified_by"] == ""
    totals = dict(group["totals"])
    assert totals["Approved"] == 1 and totals["Awaiting approval"] == 1
    pdf = client.get(f"{URL}/checklists/export?fmt=pdf&date_from=2026-03-02&date_to=2026-03-02", headers=login(MGR))
    assert pdf.content.startswith(b"%PDF")
