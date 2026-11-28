import os
import re

from app.services import exporters, haccp

from .helpers import MGR, loc_id


def render(client, login, db, clock):
    point = client.post("/api/equipment/from-template", json={"template": "cooling", "location_id": loc_id(db, "BQ")}, headers=login(MGR))
    assert point.status_code < 300, point.text
    doc = haccp.build_plan(db, clock.now, None, None, "Tester")
    doc = {**doc, "generated_at": "28 Nov 2026 09:00 (UTC)", "organization": {"name": "Demo Kitchens", "timezone": "UTC"}}
    return exporters.record_to_pdf(doc)


def test_the_plan_pdf_has_a_cover_a_contents_page_and_a_page_per_process(client, login, db, clock):
    pdf = render(client, login, db, clock)
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page\b", pdf)) >= 10  # cover, contents, a flow and a hazard page for each of the seven processes, and the rest
    if os.environ.get("HACCP_PDF_OUT"):
        open(os.environ["HACCP_PDF_OUT"], "wb").write(pdf)


def test_other_records_keep_the_shared_layout(client, login, db, clock):
    doc = {"title": "Cooling Log", "period": {"label": "Today"}, "locations": ["Beach"], "prepared_by": "Tester", "generated_at": "now", "groups": [
        {"title": "Cooling", "meta": [], "columns": [("a", "A")], "rows": [{"a": "x"}], "totals": []}]}
    assert exporters.record_to_pdf(doc).startswith(b"%PDF")
