"""The HACCP plan as one printable document: the written parts are kept in one row (see models.haccp), the control points are read from the monitoring points,
so the plan always shows the limits and frequencies the kitchens really work to."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Equipment, EquipmentSchedule, HaccpPlan, HaccpPlanVersion, Probe
from . import approvers, calibration
from .haccp_starter import starter_processes
from .records import _locations

KINDS = ("Biological", "Chemical", "Physical", "Allergen")
SHORT_LEVEL = {"ccp": "CCP", "oprp": "OPRP", "prp": "PRP"}
REVIEW = "This plan is reviewed at least once a year, and whenever a menu, process, supplier or piece of equipment changes, or after a food safety incident."

def default_content() -> dict:
    return {"owner": "", "team": "", "scope": "", "products": "", "review": REVIEW, "processes": starter_processes(), "revisions": []}


def _step(old: dict) -> dict:
    """A step as it is now: a flow step that carries its own hazards, with a decision's 'no' outcome."""
    return {"name": old.get("name", ""), "kind": old.get("kind", "step"), "control": old.get("control", ""), "no_action": old.get("no_action", ""),
            "hazards": [{"hazard": h.get("hazard", ""), "kind": h.get("kind", "Biological"), "significant": bool(h.get("significant")), "control": h.get("control", ""), "basis": h.get("basis", "")}
                        for h in old.get("hazards", [])], "no_hazard": old.get("no_hazard", "")}


def _upgraded(content: dict) -> dict:
    """A plan saved in an earlier shape (one flow, or flows with a separate hazard list) is brought to the current one without losing what was written:
    each old hazard moves to the step with its name, and any that match no step are collected on a step of their own so they are seen and placed."""
    merged = {**default_content(), **content}
    old_flow, old_hazards = content.get("flow"), content.get("hazards")
    if "processes" not in content and old_flow:
        merged["processes"] = [{"name": "All food", "steps": old_flow}]
    merged.pop("flow", None)
    merged.pop("hazards", None)
    merged["processes"] = [{"name": p.get("name", ""), "references": p.get("references", ""), "confirmed_on": p.get("confirmed_on", ""), "confirmed_by": p.get("confirmed_by", ""),
                            "steps": [_step(x) for x in p.get("steps", [])]} for p in merged["processes"]]
    unplaced = []
    for h in old_hazards or []:
        targets = [p for p in merged["processes"] if not h.get("process") or p["name"] == h["process"]] or merged["processes"][:1]
        word = (h.get("step") or "").casefold()
        found = [s for p in targets for s in p["steps"] if word and (word in s["name"].casefold() or s["name"].casefold() in word)]
        entry = _step({"hazards": [h]})["hazards"][0]
        if found:
            found[0]["hazards"].append(entry)
        else:
            unplaced.append(entry)
    if unplaced and merged["processes"]:
        merged["processes"][0]["steps"].append({"name": "Hazards not yet linked to a step", "kind": "step", "control": "", "no_action": "", "hazards": unplaced, "no_hazard": ""})
    return merged


def load(db: Session) -> tuple[dict, int, HaccpPlan | None]:
    plan = db.scalar(select(HaccpPlan).order_by(HaccpPlan.id))
    if plan is None:
        return default_content(), 0, None
    return _upgraded(plan.content), plan.version, plan


def content_of(db: Session, version: int | None) -> tuple[dict, int]:
    """The plan as it was in a given version (the current one when none is named); raises ValueError for a version that does not exist."""
    content, current, _ = load(db)
    if version is None or version == (current or 1):
        return content, current or 1
    old = db.scalar(select(HaccpPlanVersion).where(HaccpPlanVersion.version == version))
    if old is None:
        raise ValueError("There is no such version of the plan")
    return _upgraded(old.content), version


def _limit(c: EquipmentSchedule) -> str:
    if c.value_type == "yes_no":
        return "Must be Yes"
    if c.value_type == "choice":
        return "Fails on: " + ", ".join(c.fail_options or []) if c.fail_options else "Choice"
    if c.value_type != "number":
        return "Recorded"
    unit = f" {c.unit}" if c.unit else ""
    span = lambda lo, hi: f"{lo:g} to {hi:g}{unit}" if lo is not None and hi is not None else f"at least {lo:g}{unit}" if lo is not None else f"at most {hi:g}{unit}"  # noqa: E731
    if c.food_limits:
        highs = {f.get("max_value") for f in c.food_limits}
        if len(highs) == 1 and all(f.get("min_value") is not None for f in c.food_limits):  # one maximum for all: say it once
            top = f"; maximum {highs.pop():g}{unit}" if None not in highs and highs else ""
            return "Minimum by food type: " + ", ".join(f"{f['name']} {f['min_value']:g}" for f in c.food_limits) + unit + top
        return "; ".join(f"{f['name']}: {span(f.get('min_value'), f.get('max_value'))}" for f in c.food_limits)
    return span(None if c.min_value is None else float(c.min_value), None if c.max_value is None else float(c.max_value))


def _when(c: EquipmentSchedule) -> str:
    at = c.time_of_day.strftime("%H:%M") if c.time_of_day else ""
    if c.phase == "finish":
        return f"Within {c.max_open_minutes / 60:g} h of the time in" if c.max_open_minutes else "At the time out"
    if c.timing == "startup":
        return "At start-up"
    if c.timing == "interval":
        return f"Every {c.interval_minutes / 60:g} h from {at}" if c.interval_minutes else "At intervals"
    if c.timing == "manual":
        return "When needed"
    return f"Daily at {at}" if at else "At a set time"


def _control_rows(db: Session, location_ids: list[int]) -> list[dict]:
    rank = {"ccp": 0, "oprp": 1, "prp": 2}
    points = sorted(db.scalars(select(Equipment).where(Equipment.location_id.in_(location_ids), Equipment.active.is_(True))), key=lambda e: (rank.get(e.control_level, 2), e.name))
    rows = []
    for eq in points:
        reviewers = approvers.names_of(db, eq.approvers)
        for c in db.scalars(select(EquipmentSchedule).where(EquipmentSchedule.equipment_id == eq.id, EquipmentSchedule.active.is_(True)).order_by(EquipmentSchedule.id)):
            rows.append({"level": SHORT_LEVEL.get(eq.control_level, "PRP"), "point": f"{eq.name} ({eq.code})",
                         "check": (c.stage or c.parameter).replace("_", " ").capitalize(),
                         "limit": _limit(c), "when": _when(c), "records": ", ".join(eq.visible_to) if eq.visible_to else "Any employee allowed to record",
                         "review": ", ".join(reviewers) if reviewers else "Any approver at the outlet"})
    return rows


def _probe_rows(db: Session, location_ids: list[int], now: datetime) -> list[dict]:
    names = {"ok": "In date", "due_soon": "Due soon", "overdue": "Overdue", "never": "Never checked", "failed": "Failed: do not use"}
    rows = []
    for p in db.scalars(select(Probe).where(Probe.location_id.in_(location_ids), Probe.active.is_(True)).order_by(Probe.code)):
        st = calibration.status_of(db, p, now)
        rows.append({"probe": f"{p.name} ({p.code})", "status": names[st["status"]], "next": st["due_at"].strftime("%d %b %Y") if st["due_at"] else "-"})
    return rows


def _hazard_group(process: dict, index: int) -> dict:
    """The hazard analysis of one flow: a row per hazard, steps numbered as in the flow chart, so the two always agree."""
    rows = []
    for n, st in enumerate(process["steps"], 1):
        level = st["control"] or "PRP"
        label = f"{n}. {st['name']}"
        for k, hz in enumerate(st["hazards"]):
            rows.append({"step": label if k == 0 else "", "hazard": hz["hazard"], "kind": hz["kind"], "significant": "Yes" if hz["significant"] else "No", "basis": hz.get("basis") or "",
                         "control": hz["control"], "level": level if k == 0 else ""})
        if not st["hazards"]:
            rows.append({"step": label, "hazard": f"No significant hazard: {st['no_hazard']}", "kind": "", "significant": "No", "basis": "", "control": "", "level": level})
    return {"title": process["name"] if index == 0 else f"Hazard analysis: {process['name']}", "meta": [("Control level", "CCP critical control point, OPRP operational prerequisite programme, PRP managed by prerequisite programmes")],
            "columns": [("step", "Step"), ("hazard", "Hazard"), ("kind", "Type"), ("significant", "Significant"), ("basis", "Basis for the decision"), ("control", "Control measure"), ("level", "Control")],
            "rows": rows, "totals": [("Steps", len(process["steps"])), ("Significant hazards", sum(1 for st in process["steps"] for hz in st["hazards"] if hz["significant"]))],
            "empty": "No steps written yet."}


def build_plan(db: Session, now: datetime, scope: set[int] | None, location_id: int | None, prepared_by: str, version: int | None = None) -> dict:
    """The plan as a document: the current one, or an earlier version when `version` names one (the control points always show today's monitoring points)."""
    content, version = content_of(db, version)
    locations = _locations(db, scope, location_id)
    ids = [loc.id for loc in locations]
    text = lambda s: s.strip() or "Not yet written"  # noqa: E731
    details = {"title": "Plan details", "meta": [("Version", str(version)), ("Plan owner", content["owner"] or "-")],
               "columns": [("item", "Item"), ("text", "Details")], "totals": [],
               "rows": [{"item": "HACCP team", "text": text(content["team"])}, {"item": "Scope", "text": text(content["scope"])},
                        {"item": "Products and intended use", "text": text(content["products"])}]}
    processes = content["processes"] or [{"name": "Process", "references": "", "confirmed_on": "", "confirmed_by": "", "steps": []}]
    flows = [{"title": p["name"] if i == 0 else f"Process flow: {p['name']}",
              "meta": [("Reference texts", p.get("references") or "-"), ("Flow confirmed on site", f"{p['confirmed_on']} by {p['confirmed_by']}".strip() if p.get("confirmed_on") else "Not yet confirmed")],
              "columns": [("name", "Step")], "rows": [], "totals": [], "flow": p["steps"], "empty": "No process steps written yet."} for i, p in enumerate(processes)]
    hazard_groups = [_hazard_group(p, i) for i, p in enumerate(processes)]
    controls = _control_rows(db, ids)
    cp = {"title": "Control points and limits", "meta": [("Outlets", ", ".join(loc.name for loc in locations) or "-"),
                                                          ("Levels", "CCP critical control point; OPRP operational prerequisite programme; PRP prerequisite programme")],
          "columns": [("level", "Level"), ("point", "Monitoring point"), ("check", "Check"), ("limit", "Limit"), ("when", "When"), ("records", "Recorded by"), ("review", "Reviewed by")],
          "rows": controls, "totals": [(f"{level} checks", sum(1 for r in controls if r["level"] == level)) for level in ("CCP", "OPRP", "PRP")],
          "empty": "No monitoring points are set up for these outlets."}
    corrective = {"title": "Corrective action and verification", "meta": [], "columns": [("item", "Item"), ("text", "Procedure")], "totals": [],
                  "rows": [{"item": "When a check is out of limit", "text": "The reading is recorded as failed and the supervisor is alerted. The food or equipment is held or taken out of use, "
                                                                          "a corrective action is recorded against the reading, the check is repeated, and a supervisor reviews and approves the result."},
                           {"item": "Records", "text": "Every reading is kept with the person, time, thermometer used and the limit it was judged against; approvals and rejections are kept with a reason."},
                           {"item": "Review of this plan", "text": text(content["review"])}]}
    probes = _probe_rows(db, ids, now)
    thermometers = {"title": "Thermometer calibration status", "meta": [], "columns": [("probe", "Thermometer"), ("status", "Calibration"), ("next", "Next check due")], "rows": probes, "totals": [],
                    "empty": "No thermometers are registered for these outlets."}
    revisions = {"title": "Revision history", "meta": [], "columns": [("version", "Version"), ("date", "Date"), ("by", "By"), ("note", "What changed")],
                 "rows": list(reversed(content["revisions"])), "totals": [], "empty": "No revisions recorded yet."}
    chapters = [("Plan details", [details]), ("Process flow", flows), ("Hazard analysis", hazard_groups), ("Control points and limits", [cp]), ("Corrective action and verification", [corrective, thermometers]),
                ("Revision history", [revisions])]
    groups, contents = [], []
    for number, (title, found) in enumerate(chapters, 1):
        heading = f"{number}. {title}"
        contents.append(heading)
        groups += [{**found[0], "title": f"{heading}: {found[0]['title']}" if found[0]["title"] != title else heading}, *found[1:]]
    label = f"Version {version}"
    return {"kind": "haccp_plan", "title": "HACCP plan", "period": {"from": "", "to": "", "label": label}, "locations": [loc.name for loc in locations],
            "prepared_by": prepared_by, "groups": groups, "contents": contents}
