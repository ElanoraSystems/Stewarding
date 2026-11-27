from datetime import date, datetime

from .helpers import loc_id, make_lot
from .test_checklists import MGR, STEWARD, SUP
from .test_records import seed_readings
from .test_approvals import SUP_RB

URL = "/api/reports/inspector-pack?date_from=2026-03-02&date_to=2026-03-02"


def pack_doc(db, scope=None, **kw):
    from app.services.inspector_pack import build_pack
    return build_pack(db, datetime(2026, 3, 2, 12), scope, date(2026, 3, 2), date(2026, 3, 2), kw.get("location_id"), "Tester", kw.get("lots", True))


def test_pack_is_one_multi_page_pdf_with_control_points_first(client, login, db, clock):
    seed_readings(client, login)
    h = login(MGR)
    eq = next(e for e in client.get("/api/monitoring/equipment", headers=h).json() if e["code"] == "DW-MK-1")
    assert client.put(f"/api/equipment/{eq['id']}", json={"control_level": "ccp"}, headers=h).status_code == 200
    res = client.get(URL, headers=h)
    assert res.status_code == 200 and res.content.startswith(b"%PDF") and "inspector-pack-2026-03-02" in res.headers["content-disposition"]
    assert res.content.count(b"/Type /Page\n") + res.content.count(b"/Type /Page ") + res.content.count(b"/Type/Page") > 3  # cover, summary, monitoring ...
    doc = pack_doc(db)
    chapters = [g["chapter"] for g in doc["groups"] if g.get("chapter")]
    assert chapters[0] == "1. Summary" and chapters[1].startswith("2. Monitoring") and chapters[2].startswith("3. Corrective actions")
    assert chapters[3].startswith("4. Probe calibration") and chapters[4].startswith("5. Checklist") and chapters[5].startswith("6. Approvals")
    monitoring = doc["groups"][1:next(i for i, g in enumerate(doc["groups"]) if g.get("chapter", "").startswith("3."))]
    assert "DW-MK-1" in monitoring[0]["title"] and "CCP" in monitoring[0]["title"] and len(monitoring) > 1
    summary = {r["measure"]: r["count"] for r in doc["groups"][0]["rows"]}
    assert summary["Monitoring readings"] == 2 and summary["Readings outside their limit"] == 1 and summary["Corrective actions"] == 1
    actions = next(g for g in doc["groups"] if g["title"].endswith("Corrective actions"))
    assert "Descaled the heater" in actions["rows"][0]["action"] and dict(actions["totals"])["Open"] == 1


def test_empty_sections_say_so_and_training_is_skipped(client, login, db, clock):
    doc = pack_doc(db)
    notes = [g["empty"] for g in doc["groups"] if g.get("empty") and not g["rows"] and g["columns"] == [("note", "")]]
    assert "No corrective actions were taken in this period." in notes and "No probe calibration checks in this period." in notes
    assert not any("training" in c.lower() for c in doc["contents"])
    assert client.get(URL, headers=login(MGR)).content.startswith(b"%PDF")


def test_lots_chapter_follows_lot_permission(client, login, db, clock):
    make_lot(loc_id(db, "MK"))
    assert any(c.endswith("Lot register") for c in pack_doc(db)["contents"])
    assert not any(c.endswith("Lot register") for c in pack_doc(db, lots=False)["contents"])


def test_permission_scope_and_limits(client, login, db, clock):
    seed_readings(client, login)
    assert client.get(URL, headers=login(STEWARD)).status_code == 403
    assert client.get(f"{URL}&location_id={loc_id(db, 'MK')}", headers=login(SUP_RB)).status_code == 403
    assert client.get(f"{URL}&location_id=999999", headers=login(MGR)).status_code == 404
    assert client.get("/api/reports/inspector-pack?date_from=2026-03-05&date_to=2026-03-01", headers=login(MGR)).status_code == 400
    assert client.get("/api/reports/inspector-pack?date_from=2025-01-01&date_to=2026-03-01", headers=login(MGR)).status_code == 400
    mk = pack_doc(db, scope={loc_id(db, "RB")})  # a supervisor of the other outlet sees none of the main kitchen's readings
    assert mk["locations"] == ["Rooftop Bar"] and {r["measure"]: r["count"] for r in mk["groups"][0]["rows"]}["Monitoring readings"] == 0


def test_training_chapter_lists_certificates_when_someone_finished_a_course(client, login, db, clock):
    from sqlalchemy import select
    from app.models import Employee, EmployeeLocation, TrainingAssignment, TrainingCourse, User
    emp = db.scalar(select(Employee).join(EmployeeLocation, EmployeeLocation.employee_id == Employee.id).where(EmployeeLocation.location_id == loc_id(db, "MK")))
    uid = db.scalar(select(User.id))
    course = TrainingCourse(title="Food hygiene level 2", created_by=uid)
    db.add(course)
    db.flush()
    db.add(TrainingAssignment(course_id=course.id, employee_id=emp.id, assigned_by=uid, completed_at=datetime(2026, 3, 2, 9), certificate_no="CERT-1", score=90))
    db.commit()
    doc = pack_doc(db)
    group = next(g for g in doc["groups"] if g["title"] == "Training completed")
    assert group["rows"][0]["certificate"] == "CERT-1" and group["rows"][0]["course"] == "Food hygiene level 2"
    assert any(c.endswith("Staff training") for c in doc["contents"])
    assert client.get(URL, headers=login(MGR)).content.startswith(b"%PDF")
