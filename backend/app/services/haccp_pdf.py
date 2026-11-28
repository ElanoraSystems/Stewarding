"""The HACCP plan as a controlled document: a cover with document control and sign-off, a contents page, one chapter per section and a flow and hazard
analysis page per process. Only the plan uses this look; every other report keeps the shared layout in exporters.py. Colour carries meaning here:
red is a critical control point, amber an operational prerequisite programme, everything else is ink and grey with one dark accent."""
import io
import re
from functools import partial

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents

from .exporters import MARGIN, PAGE, FlowChart, _esc, _Numbered, _org_lines, _weights

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#616e7c")
RULE = colors.HexColor("#d5dbe1")
HEAD_BG = colors.HexColor("#eef1f4")
ACCENT = colors.HexColor("#1f3a5f")
WHITE = colors.white
CCP = (colors.HexColor("#fdecea"), colors.HexColor("#b42318"))  # tint, then text and line
OPRP = (colors.HexColor("#fff4dc"), colors.HexColor("#8a5a00"))
PRP = (HEAD_BG, MUTED)
LEVELS = {"CCP": CCP, "OPRP": OPRP, "PRP": PRP}
BAND_NAMES = {"CCP": "Critical control points (CCP)", "OPRP": "Operational prerequisite programmes (OPRP)", "PRP": "Prerequisite programmes (PRP)"}
STATUS_TEXT = {"in date": "#1a7f4b", "due soon": "#8a5a00", "overdue": "#b42318", "never checked": "#b42318", "failed: do not use": "#b42318"}
WEIGHTS = {"step": 1.5, "hazard": 3, "kind": 0.9, "significant": 0.85, "basis": 2.2, "control": 2.6, "level": 0.8, "point": 2.4, "check": 1.5, "limit": 2.4, "when": 1.5,
           "records": 1.6, "review": 1.6, "probe": 3, "status": 1.3, "next": 1.3, "version": 0.7, "date": 1, "by": 1.4, "note": 5}
SAME_FOR_ALL = {"records", "review"}  # said once under the table when every row reads the same


def _hex(colour) -> str:
    return colour.hexval()[2:]


class HaccpFlow(FlowChart):
    """The shared flow chart in the plan's palette: plain boxes, larger text, red and amber only for control steps."""

    BOX_H, FONT = 46, 8
    PLAIN = (WHITE, colors.HexColor("#52606d"))
    TINT = {"CCP": CCP, "OPRP": OPRP}


class _Chapter(Paragraph):
    """A chapter heading, which the contents page picks up with its page number."""


class _Doc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, _Chapter):
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]

    def make(name: str, font: str = "Helvetica", colour=INK, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, fontName=font, textColor=colour, **kw)

    return {
        "cover": make("cover", "Helvetica-Bold", ACCENT, fontSize=36, leading=40),
        "kicker": make("kicker", "Helvetica-Bold", MUTED, fontSize=9, leading=12, spaceAfter=4),
        "lead": make("lead", colour=MUTED, fontSize=13, leading=18),
        "orgname": make("orgname", "Helvetica-Bold", fontSize=15, leading=18),
        "org": make("org", colour=MUTED, fontSize=8.5, leading=11),
        "chapter": make("chapter", "Helvetica-Bold", ACCENT, fontSize=21, leading=25, spaceAfter=2),
        "sub": make("sub", "Helvetica-Bold", fontSize=13, leading=17, spaceBefore=2),
        "label": make("label", "Helvetica-Bold", MUTED, fontSize=7.2, leading=9),
        "value": make("value", fontSize=10, leading=13),
        "cell": make("cell", fontSize=8.8, leading=11.4),
        "head": make("head", "Helvetica-Bold", fontSize=8, leading=10),
        "small": make("small", colour=MUTED, fontSize=8.2, leading=11),
        "toc": make("toc", fontSize=11, leading=20),
    }


def _masthead(org: dict, st: dict, width: float) -> list:
    lines = _org_lines(org)
    if not lines:
        return []
    text = [Paragraph(_esc(lines[0]), st["orgname"])] + [Paragraph(_esc(line), st["org"]) for line in lines[1:]]
    logo = None
    if org.get("logo_path"):
        w, h = ImageReader(org["logo_path"]).getSize()
        logo = Image(org["logo_path"], width=44 * w / h, height=44)
    left = (logo.drawWidth + 14) if logo else 0.1
    table = Table([[logo or "", text]], colWidths=[left, width - left])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 0)]))
    return [table]


def _control(st: dict, pairs: list[tuple[str, str]], width: float) -> Table:
    """The document-control block: label over value in a ruled grid."""
    per_row = 3
    cells = [[Paragraph(_esc(label).upper(), st["label"]), Paragraph(_esc(value) or "-", st["value"])] for label, value in pairs]
    rows = [cells[i:i + per_row] + [""] * (per_row - len(cells[i:i + per_row])) for i in range(0, len(cells), per_row)]
    table = Table(rows, colWidths=[width / per_row] * per_row)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 1.2, ACCENT), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return table


def _signoff(st: dict, width: float, owner: str) -> Table:
    names = [f"Plan owner{(': ' + owner) if owner and owner != '-' else ''}", "Approved by (management)", "Date"]
    gap, third = width * 0.04, width * 0.28
    cols = [third, gap, third, gap, width - 2 * third - 2 * gap]
    table = Table([["", "", "", "", ""], [Paragraph(_esc(names[0]), st["small"]), "", Paragraph(names[1], st["small"]), "", Paragraph(names[2], st["small"])]],
                  colWidths=cols, rowHeights=[38, None])
    table.setStyle(TableStyle([("LINEBELOW", (c, 0), (c, 0), 0.7, INK) for c in (0, 2, 4)] + [("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 1), (-1, 1), 4)]))
    return table


def _key(st: dict, width: float) -> Table:
    """How to read the plan, printed once."""
    rows = [("CCP", "Critical control point. A step where a failed limit makes the food unsafe, so it is checked and recorded every time.", CCP),
            ("OPRP", "Operational prerequisite programme. A control that is not a critical limit but is monitored and recorded.", OPRP),
            ("PRP", "Prerequisite programme. Basic hygiene and housekeeping controls, managed through the checklists.", PRP),
            ("Significant", "A hazard likely enough, and serious enough, to need a control. The basis for each decision is written in the hazard analysis.", (HEAD_BG, INK))]
    data = [[Paragraph(f'<font color="#{_hex(tone[1])}"><b>{name}</b></font>', st["cell"]), Paragraph(_esc(text), st["cell"])] for name, text, tone in rows]
    table = Table(data, colWidths=[width * 0.14, width * 0.86])
    table.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), tone[0]) for i, (_, _, tone) in enumerate(rows)] +
                              [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 1, WHITE), ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return table


def _cell(key: str, value, st: dict):
    text = "" if value is None else str(value)
    if key == "level" and text:
        return Paragraph(f'<font color="#{_hex(LEVELS.get(text, PRP)[1])}"><b>{_esc(text)}</b></font>', st["cell"])
    if key == "significant":
        return Paragraph(f"<b>{_esc(text)}</b>" if text == "Yes" else f'<font color="#{_hex(MUTED)}">{_esc(text)}</font>', st["cell"])
    if key == "status" and text.lower() in STATUS_TEXT:
        return Paragraph(f'<font color="{STATUS_TEXT[text.lower()]}"><b>{_esc(text)}</b></font>', st["cell"])
    if key == "basis" and text:
        return Paragraph(f'<font color="#{_hex(MUTED)}" size="7.8">{_esc(text)}</font>', st["cell"])
    if key == "step" and text:
        return Paragraph(f"<b>{_esc(text)}</b>", st["cell"])
    return Paragraph(_esc(text), st["cell"])


def _table(group: dict, st: dict, width: float) -> list:
    """A group's rows as a clean table, with any note that belongs under it."""
    rows, columns, notes = group["rows"], list(group["columns"]), []
    if not rows:
        return [Paragraph(f"<i>{_esc(group.get('empty', 'Nothing recorded'))}</i>", st["small"])]
    if [key for key, _ in columns] == ["item", "text"]:  # a list of headed paragraphs, no header row needed
        data = [[Paragraph(f"<b>{_esc(r['item'])}</b>", st["cell"]), Paragraph(_esc(r["text"]).replace("\n", "<br/>"), st["cell"])] for r in rows]
        table = Table(data, colWidths=[width * 0.2, width * 0.8])
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("LINEABOVE", (0, 0), (-1, 0), 1, ACCENT),
                                   ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return [table]
    for key, label in list(columns):
        values = {str(r.get(key) or "") for r in rows}
        if values == {""}:  # a column nobody filled in is not printed
            columns.remove((key, label))
        elif key in SAME_FOR_ALL and len(values) == 1 and len(rows) > 1:
            columns.remove((key, label))
            notes.append(f"{label}: {values.pop()}")
    bands = None
    if any(k == "level" for k, _ in columns) and any(k == "point" for k, _ in columns):  # control points sit under their level instead of a Level column
        columns = [c for c in columns if c[0] != "level"]
        bands = [(level, [r for r in rows if r["level"] == level]) for level in ("CCP", "OPRP", "PRP")]
        bands = [(level, found) for level, found in bands if found]
    keys = [k for k, _ in columns]
    weights = [WEIGHTS.get(k) or w for (k, _), w in zip(columns, _weights({"rows": rows, "columns": columns}))]
    widths = [width * w / sum(weights) for w in weights]
    data = [[Paragraph(_esc(label), st["head"]) for _, label in columns]]
    style = [("BACKGROUND", (0, 0), (-1, 0), HEAD_BG), ("LINEABOVE", (0, 0), (-1, 0), 1.2, ACCENT), ("LINEBELOW", (0, 0), (-1, 0), 0.6, MUTED)]
    for level, found in (bands or [(None, rows)]):
        if level:
            data.append([Paragraph(f'<font color="#{_hex(LEVELS[level][1])}"><b>{BAND_NAMES[level]}</b></font>', st["cell"])] + [""] * (len(keys) - 1))
            style += [("SPAN", (0, len(data) - 1), (-1, len(data) - 1)), ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), LEVELS[level][0])]
        for r in found:
            data.append([_cell(k, r.get(k), st) for k in keys])
            if "step" in keys and r.get("step") and len(data) > 2:  # a new step starts under a rule, its further hazards follow without one
                style.append(("LINEABOVE", (0, len(data) - 1), (-1, len(data) - 1), 0.6, RULE))
            if r.get("level") in ("CCP", "OPRP") and "level" in keys:
                at = (keys.index("level"), len(data) - 1)
                style.append(("BACKGROUND", at, at, LEVELS[r["level"]][0]))
    style += [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6),
              ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, -1), (-1, -1), 0.8, MUTED)]
    if "step" not in keys:
        style.append(("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE))
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    return [table, *([Spacer(1, 5), Paragraph(" &nbsp;|&nbsp; ".join(_esc(n) for n in notes), st["small"])] if notes else [])]


def _furniture(org_name: str, version: str):
    def draw(canv, document):
        width, height = PAGE
        canv.saveState()
        canv.setFillColor(ACCENT)
        canv.rect(0, height - 5, width, 5, stroke=0, fill=1)
        if document.page > 1:
            canv.setFont("Helvetica-Bold", 8)
            canv.setFillColor(INK)
            canv.drawString(MARGIN, height - 24, org_name)
            canv.setFont("Helvetica", 8)
            canv.setFillColor(MUTED)
            canv.drawRightString(width - MARGIN, height - 24, f"HACCP plan  |  {version}")
            canv.setStrokeColor(RULE)
            canv.line(MARGIN, height - 29, width - MARGIN, height - 29)
        canv.setStrokeColor(RULE)
        canv.line(MARGIN, 27, width - MARGIN, 27)
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(MUTED)
        canv.drawString(MARGIN, 15, "Controlled document. Check the version before use; printed copies are not updated.")
        canv.restoreState()

    return draw


def _facts(doc: dict) -> dict:
    """What the cover needs, read from the plan's own groups so the layout stays independent of how the plan is built."""
    groups = doc["groups"]
    details = next((g for g in groups if g["title"].endswith("Plan details")), {"meta": []})
    meta = dict(details["meta"])
    version = meta.get("Version") or doc["period"]["label"].split()[-1]
    control = next((g for g in groups if "Control points" in g["title"]), {"meta": []})
    revisions = next((g for g in groups if g["title"].endswith("Revision history")), {"rows": []})
    mine = next((r for r in revisions["rows"] if str(r.get("version")) == str(version)), None)
    return {"version": version, "owner": meta.get("Plan owner") or "-", "outlets": dict(control["meta"]).get("Outlets") or ", ".join(doc["locations"]) or "-",
            "revised": f"{mine['date']}, {mine['by']}" if mine else "Not yet saved"}


def haccp_to_pdf(doc: dict) -> bytes:
    st, width, org = _styles(), PAGE[0] - 2 * MARGIN, doc.get("organization") or {}
    facts = _facts(doc)
    version = f"Version {facts['version']}"
    story = [Spacer(1, 6), *_masthead(org, st, width), Spacer(1, 62), Paragraph("FOOD SAFETY MANAGEMENT", st["kicker"]), Paragraph("HACCP Plan", st["cover"]),
             Paragraph(_esc(f"{version}  |  {facts['outlets']}"), st["lead"]), Spacer(1, 38),
             _control(st, [("Version", facts["version"]), ("Plan owner", facts["owner"]), ("Last revised", facts["revised"]), ("Outlets", facts["outlets"]),
                           ("Printed by", doc["prepared_by"]), ("Printed on", str(doc.get("generated_at") or ""))], width),
             Spacer(1, 40), _signoff(st, width, facts["owner"]), PageBreak(), Paragraph("Contents", st["chapter"]), Spacer(1, 10)]
    toc = TableOfContents()
    toc.levelStyles = [st["toc"]]
    toc.dotsMinLevel = 0
    story += [toc, Spacer(1, 26), Paragraph("How to read this plan", st["sub"]), Spacer(1, 6), _key(st, width)]
    seen: set[tuple] = set()
    for group in doc["groups"]:
        title = group["title"]
        numbered = re.match(r"^\d+\. ([^:]*)(?:: (.*))?$", title)
        label, _, sub = title.partition(": ")
        if numbered:  # a chapter starts on its own page; its first process or part is headed under it
            story += [PageBreak(), _Chapter(_esc(title.split(": ")[0]), st["chapter"])]
            sub = numbered.group(2) or ""
        elif sub:  # a further process in the same chapter starts on a new page under a small label
            story += [PageBreak(), Paragraph(_esc(label).upper(), st["kicker"])]
        else:
            sub = title
            story.append(Spacer(1, 18))
        if sub:
            story.append(Paragraph(_esc(sub), st["sub"]))
        story.append(Spacer(1, 6))
        for name, value in group.get("meta") or []:  # a fact, said once; the level legend is on the contents page
            if (name, value) not in seen and name not in ("Levels", "Control level"):
                seen.add((name, value))
                story.append(Paragraph(f"{_esc(name)}: <b>{_esc(value)}</b>", st["small"]))
        if group.get("totals"):
            story.append(Paragraph("  |  ".join(f"{_esc(name)}: <b>{_esc(value)}</b>" for name, value in group["totals"]), st["small"]))
        story.append(Spacer(1, 8))
        if group.get("flow") is not None:
            steps = group["flow"]
            if not steps:
                story.append(Paragraph(f"<i>{_esc(group.get('empty', ''))}</i>", st["small"]))
            pages = -(-len(steps) // 20)
            size = -(-(-(-len(steps) // pages)) // 5) * 5  # evenly over the pages it needs, whole rows of five
            for n in range(0, len(steps), size):
                if n:
                    story += [PageBreak(), Paragraph(_esc(f"{sub or label} (continued)"), st["sub"]), Spacer(1, 8)]
                story.append(HaccpFlow(steps[n:n + size], first=n + 1))
            if ("flow-note",) not in seen:
                seen.add(("flow-note",))
                story += [Spacer(1, 8), Paragraph("Red steps are critical control points (CCP) and amber steps are operational prerequisite programmes (OPRP). A dashed box is a question: "
                                                  "the line to the right is Yes and the box below says what happens on No.", st["small"])]
        else:
            story += _table(group, st, width)
    buf = io.BytesIO()
    pdf = _Doc(buf, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=42, bottomMargin=38, title="HACCP plan", author=doc.get("prepared_by") or "")
    frame = Frame(MARGIN, 38, width, PAGE[1] - 80, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    pdf.addPageTemplates([PageTemplate("all", [frame], onPage=_furniture(org.get("name") or "", version))])
    pdf.multiBuild(story, canvasmaker=partial(_Numbered, generated=str(doc.get("generated_at") or "")))
    return buf.getvalue()
