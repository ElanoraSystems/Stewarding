import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
