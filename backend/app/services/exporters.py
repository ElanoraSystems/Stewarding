import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe(value):
    """Stops spreadsheet apps from running text that starts like a formula."""
    if isinstance(value, str) and value[:1] in FORMULA_PREFIXES:
        return "'" + value
    return value


def _header(report: dict) -> list[tuple[str, str]]:
    period = report["period"]
    return [("Report", f"{period['type'].title()} report"), ("Period", f"{period['label']} ({period['from']} to {period['to']})"),
            ("Locations", ", ".join(report["locations"])), ("Time zones", ", ".join(report["timezones"])),
            ("Generated at (UTC)", report["generated_at"])]


def to_csv(report: dict) -> bytes:
    buf = io.StringIO()
    out = csv.writer(buf)
    for label, value in _header(report):
        out.writerow([label, safe(value)])
    for sec in report["sections"]:
        out.writerow([])
        out.writerow([safe(sec["title"])])
        out.writerow([safe(c["label"]) for c in sec["columns"]])
        for row in sec["rows"]:
            out.writerow([safe(row.get(c["key"])) for c in sec["columns"]])
        for total in sec["totals"]:
            out.writerow([safe(total["label"]), safe(total["value"])])
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(report: dict) -> bytes:
    book = Workbook()
    info = book.active
    info.title = "Report"
    for label, value in _header(report):
        info.append([label, safe(value)])
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 70
    used = {"Report"}
    for index, sec in enumerate(report["sections"], 1):
        name = "".join(ch for ch in sec["title"] if ch not in "[]:*?/\\")[:28] or f"Section {index}"
        while name in used:
            name = f"{name[:25]}_{index}"
        used.add(name)
        sheet = book.create_sheet(name)
        sheet.append([safe(c["label"]) for c in sec["columns"]])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in sec["rows"]:
            sheet.append([safe(row.get(c["key"])) for c in sec["columns"]])
        for total in sec["totals"]:
            sheet.append([])
            sheet.append([safe(total["label"]), safe(total["value"])])
        for i in range(len(sec["columns"])):
            sheet.column_dimensions[chr(65 + i % 26)].width = 20
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def to_pdf(report: dict) -> bytes:
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell", fontSize=7, leading=8)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24,
                            title=f"{report['period']['type'].title()} report")
    story = [Paragraph(f"{report['period']['type'].title()} operations report", styles["Title"])]
    story += [Paragraph(f"<b>{label}:</b> {_esc(value)}", styles["Normal"]) for label, value in _header(report)[1:]]
    for sec in report["sections"]:
        story += [Spacer(1, 12), Paragraph(_esc(sec["title"]), styles["Heading3"])]
        if not sec["rows"]:
            story.append(Paragraph("No records for this period.", styles["Normal"]))
        else:
            data = [[Paragraph(f"<b>{_esc(c['label'])}</b>", cell) for c in sec["columns"]]]
            data += [[Paragraph(_esc(row.get(c["key"])), cell) for c in sec["columns"]] for row in sec["rows"]]
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef0")),
                                       ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(table)
        if sec["totals"]:
            story.append(Paragraph(" | ".join(f"<b>{_esc(t['label'])}:</b> {_esc(t['value'])}" for t in sec["totals"]), styles["Normal"]))
    doc.build(story)
    return buf.getvalue()


def _esc(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


WIDE = {"corrective_action": 3, "task": 3, "comment": 2, "approved_by": 2, "check": 1.8, "verified_by": 1.5, "limits": 1.4,
        "measure": 1.5, "date": 1.3, "time": 0.8, "result": 0.9, "value": 1.1}


def _mark(key: str, value) -> str:
    text = _esc(value)
    return f'<font color="#b91c1c"><b>{text}</b></font>' if key == "result" and value == "FAIL" else text


def _record_meta(doc: dict) -> list[tuple[str, str]]:
    return [("Period", doc["period"]["label"]), ("Locations", ", ".join(doc["locations"]) or "-"),
            ("Prepared by", doc["prepared_by"]), ("Generated", doc["generated_at"])]


def record_to_csv(doc: dict) -> bytes:
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow([safe(doc["title"])])
    for label, value in _record_meta(doc):
        out.writerow([label, safe(value)])
    for group in doc["groups"]:
        out.writerow([])
        out.writerow([safe(group["title"])])
        out.writerow([safe(label) for _, label in group["columns"]])
        for row in group["rows"]:
            out.writerow([safe(row.get(key)) for key, _ in group["columns"]])
        for label, value in group["totals"]:
            out.writerow([label, value])
    return buf.getvalue().encode("utf-8-sig")


def record_to_xlsx(doc: dict) -> bytes:
    book = Workbook()
    book.remove(book.active)
    used: set[str] = set()
    for index, group in enumerate(doc["groups"] or [{"title": "No records", "meta": [], "columns": [], "rows": [], "totals": []}], 1):
        name = "".join(ch for ch in group["title"] if ch not in "[]:*?/\\")[:28] or f"Sheet {index}"
        while name in used:
            name = f"{name[:25]}_{index}"
        used.add(name)
        sheet = book.create_sheet(name)
        sheet.append([safe(doc["title"])])
        sheet["A1"].font = Font(bold=True, size=14)
        sheet.append([safe(group["title"])])
        sheet["A2"].font = Font(bold=True)
        for label, value in [*_record_meta(doc), *group["meta"]]:
            sheet.append([label, safe(value)])
        sheet.append([])
        header_row = sheet.max_row + 1
        sheet.append([safe(label) for _, label in group["columns"]])
        for cell in sheet[header_row]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="E8EEF0")
        for row in group["rows"]:
            sheet.append([safe(row.get(key)) for key, _ in group["columns"]])
        sheet.append([])
        for label, value in group["totals"]:
            sheet.append([label, value])
        sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
        for i, (key, _) in enumerate(group["columns"]):
            sheet.column_dimensions[chr(65 + i % 26)].width = 16 * WIDE.get(key, 1)
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def record_to_pdf(doc: dict) -> bytes:
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell", fontSize=7.5, leading=9)
    head = cell.clone("head", fontName="Helvetica-Bold")
    title_style = styles["Title"].clone("record_title", fontSize=20, leading=24)
    buf = io.BytesIO()
    page = landscape(A4)
    width = page[0] - 48

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(24, 14, f"{doc['title']} - {doc['period']['label']}")
        canvas.drawRightString(page[0] - 24, 14, f"Page {document.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(buf, pagesize=page, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=30, title=doc["title"])
    story = [Paragraph(_esc(doc["title"]), title_style)]
    info = Table([[Paragraph(f"<b>{_esc(label)}</b>", cell), Paragraph(_esc(value), cell)] for label, value in _record_meta(doc)],
                 colWidths=[90, width - 90])
    info.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8eef0"))]))
    story.append(info)
    if not doc["groups"]:
        story += [Spacer(1, 14), Paragraph("No records for this period.", styles["Normal"])]
    for group in doc["groups"]:
        weights = [WIDE.get(key, 1) for key, _ in group["columns"]]
        widths = [width * w / sum(weights) for w in weights]
        story += [Spacer(1, 14), Paragraph(_esc(group["title"]), styles["Heading3"]),
                  Paragraph(" | ".join(f"<b>{_esc(label)}:</b> {_esc(value)}" for label, value in group["meta"]), styles["Normal"]),
                  Spacer(1, 4)]
        data = [[Paragraph(_esc(label), head) for _, label in group["columns"]]]
        data += [[Paragraph(_mark(key, row.get(key)), cell) for key, _ in group["columns"]] for row in group["rows"]]
        table = Table(data, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef0")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                 ("VALIGN", (0, 0), (-1, -1), "TOP")]
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 4),
                  Paragraph(" | ".join(f"<b>{_esc(label)}:</b> {_esc(value)}" for label, value in group["totals"]), styles["Normal"])]
    sign = Table([["Prepared by", "", "Reviewed and approved by", "", "Date", ""]], colWidths=[width * f for f in (.12, .22, .2, .22, .06, .18)],
                 rowHeights=28)
    sign.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#e8eef0")),
                              ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#e8eef0")), ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#e8eef0"))]))
    story += [Spacer(1, 22), KeepTogether(sign)]
    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
