import io

from openpyxl import load_workbook

from .test_checklists import MGR, STEWARD, SUP
from .test_monitoring import mk_stage, record
from .test_records import URL, monitoring, seed_readings
from .helpers import loc_id


def grid_group(doc):
    return next(g for g in doc["groups"] if "DW-MK-1" in g["title"])


def test_a_log_measured_several_ways_in_one_visit_reads_as_one_row_with_a_column_for_each(client, login, db, clock):
    seed_readings(client, login)  # a wash of 60 and a final rinse of 70 (which fails) recorded together
    doc = monitoring(client, login(MGR), location_id=loc_id(db, "MK")).json()
    group = grid_group(doc)
    assert group["layout"] == "grid" and len(group["rows"]) == 1  # not one line for the wash and another for the rinse
    labels = [label for _, label in group["columns"]]
    assert labels[:2] == ["Date", "Time"] and any(l.startswith("Wash") for l in labels) and any(l.startswith("Final rinse") for l in labels)
    row = group["rows"][0]
    values = {label: row[key] for key, label in group["columns"]}
    assert values["Wash (°C)"] == "60 °C" and values["Final rinse (°C)"] == "70 °C" and values["Result"] == "FAIL"
    assert row["date"] == "02 Mar 2026" and row["recorded_by"] == "Sid Steward" and "Descaled the heater" in row["corrective_action"]
    tones = row["_tone"]
    wash_key = next(k for k, l in group["columns"] if l == "Wash (°C)")
    rinse_key = next(k for k, l in group["columns"] if l == "Final rinse (°C)")
    assert (tones[wash_key], tones[rinse_key], tones["result"]) == ("ok", "bad", "bad")  # the failed rinse and the result stand out
    totals = dict(group["totals"])
    assert totals["Checks recorded"] == 1 and totals["Failed"] == 1 and totals["Passed"] == 0
    assert totals["Wash (°C): lowest to highest"] == "60 to 60"


def test_the_line_by_line_layout_is_still_available(client, login, db, clock):
    seed_readings(client, login)
    group = grid_group(monitoring(client, login(MGR), location_id=loc_id(db, "MK"), layout="lines").json())
    assert group.get("layout") != "grid" and len(group["rows"]) == 2 and "check" in dict(group["columns"])
    assert client.get(f"{URL}/monitoring?date_from=2026-03-02&date_to=2026-03-02&layout=sideways", headers=login(MGR)).status_code == 422


def test_a_retest_is_its_own_row_and_a_log_with_one_measurement_stays_one_row_per_check(client, login, db, clock):
    steward = login(STEWARD)
    eq, wash = mk_stage(client, steward)
    _, rinse = mk_stage(client, steward, "final_rinse")
    record(client, steward, eq, wash, 60)
    failed = record(client, steward, eq, rinse, 70, corrective_action="Descaled the heater").json()
    clock.advance(minutes=20)
    assert record(client, steward, eq, rinse, 85, retest_of_id=failed["id"]).status_code == 201  # the rinse again after the fix is a new visit
    group = grid_group(monitoring(client, login(MGR), location_id=loc_id(db, "MK")).json())
    assert len(group["rows"]) == 2
    first, second = group["rows"]
    assert first["result"] == "FAIL" and second["result"] == "Pass" and second["_tone"]["result"] == "ok"
    singles = [g for g in monitoring(client, login(MGR), location_id=loc_id(db, "MK")).json()["groups"] if g.get("layout") == "grid"]
    assert all(len(g["rows"]) >= 1 for g in singles)  # only logs with several measurements in a visit are laid out this way


def test_the_grid_downloads_as_excel_and_pdf_with_tinted_cells(client, login, db, clock):
    seed_readings(client, login)
    h = login(MGR)
    xlsx = client.get(f"{URL}/monitoring/export?fmt=xlsx&date_from=2026-03-02&date_to=2026-03-02", headers=h)
    book = load_workbook(io.BytesIO(xlsx.content))
    sheet = next(s for s in book.worksheets if "DW-MK-1" in s.title or any("Wash" in str(c.value) for row in s.iter_rows() for c in row))
    fills = {c.fill.fgColor.rgb[-6:] for row in sheet.iter_rows() for c in row if c.fill and c.fill.fill_type == "solid"}
    assert "FBDCDC" in fills  # the failed rinse is shaded red
    pdf = client.get(f"{URL}/monitoring/export?fmt=pdf&date_from=2026-03-02&date_to=2026-03-02", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    csv = client.get(f"{URL}/monitoring/export?fmt=csv&date_from=2026-03-02&date_to=2026-03-02", headers=h)
    assert csv.status_code == 200 and b"_tone" not in csv.content


def oil_day(client, login, db, clock, day, tpm, look):
    from .test_tpm_oil import fryer
    clock.set(2026, 3, day, 12, 0)  # 16:00 in Dubai, after the 15:00 test time opens
    point = next((p for p in client.get("/api/monitoring/equipment", headers=login(MGR)).json() if p["kind"] == "Frying oil"), None) or fryer(client, login(MGR), db)
    by = {s["stage"]: s for s in point["schedules"]}
    form = [{"schedule_id": by["TPM reading"]["id"], "value": tpm}, {"schedule_id": by["Oil temperature"]["id"], "value": 178},
            {"schedule_id": by["Oil look and smell"]["id"], "answer": look}]
    done = client.post("/api/monitoring/readings/batch", json={"equipment_id": point["id"], "readings": form}, headers=login(STEWARD))
    assert done.status_code == 201, done.text
    return point


def test_the_frying_oil_report_is_one_row_a_day_with_tpm_temperature_and_condition_side_by_side(client, login, db, clock):
    for day, tpm, look in ((2, 14.5, "Normal"), (3, 21.0, "Dark"), (4, 26.5, "Foaming")):
        oil_day(client, login, db, clock, day, tpm, look)
    doc = client.get(f"{URL}/monitoring?date_from=2026-03-02&date_to=2026-03-04&equipment_kind=Frying%20oil", headers=login(MGR)).json()
    group = doc["groups"][0]
    assert group["layout"] == "grid" and len(group["rows"]) == 3  # three days, three rows, not nine lines
    labels = [label for _, label in group["columns"]]
    assert labels[:5] == ["Date", "Time", "TPM reading (%)", "Oil temperature (°C)", "Oil look and smell"]
    tpm, temp, look = (next(k for k, l in group["columns"] if l == name) for name in labels[2:5])
    rows = group["rows"]
    assert [r[tpm] for r in rows] == ["14.5 %", "21 %", "26.5 %"] and [r[look] for r in rows] == ["Normal", "Dark", "Foaming"]
    assert [r["_tone"][tpm] for r in rows] == ["ok", "warn", "bad"]  # fine, close to the limit (amber from 20%), outside it
    assert [r["result"] for r in rows] == ["Pass", "Pass", "FAIL"]
    assert dict(group["totals"])["TPM reading (%): lowest to highest"] == "14.5 to 26.5"
    assert rows[2]["corrective_action"].count("action required") == 1  # TPM and condition both failed but the action is listed once
