"""The HACCP plan as one printable document: the written parts are kept in one row (see models.haccp), the control points are read from the monitoring points,
so the plan always shows the limits and frequencies the kitchens really work to."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Equipment, EquipmentSchedule, HaccpPlan, HaccpPlanVersion, Probe
from . import approvers, calibration
from .records import _locations

KINDS = ("Biological", "Chemical", "Physical", "Allergen")
SHORT_LEVEL = {"ccp": "CCP", "oprp": "OPRP", "prp": "PRP"}
REVIEW = "This plan is reviewed at least once a year, and whenever a menu, process, supplier or piece of equipment changes, or after a food safety incident."

# A starting point written in general terms; the food safety lead edits it to the kitchen's own menu and processes.
STARTER_HAZARDS = [
    {"step": "Receiving", "hazard": "Food arrives too warm, damaged or past its date; contamination in transit", "kind": "Biological", "significant": True,
     "control": "Check delivery temperature, packaging, labels and dates at the door; reject what is out of limit."},
    {"step": "Cold storage", "hazard": "Bacteria grow if storage is too warm; raw food contaminates ready-to-eat food", "kind": "Biological", "significant": True,
     "control": "Chillers checked at set times against their limits; raw food stored below ready-to-eat food."},
    {"step": "Frozen storage", "hazard": "Food thaws and refreezes if a freezer is too warm", "kind": "Biological", "significant": False,
     "control": "Freezers checked at set times against their limits."},
    {"step": "Defrosting", "hazard": "Bacteria grow while food thaws", "kind": "Biological", "significant": True,
     "control": "Time in and time out recorded; food defrosts under refrigeration within the time allowed."},
    {"step": "Cooking", "hazard": "Pathogens survive if the core does not reach the limit", "kind": "Biological", "significant": True,
     "control": "Core temperature measured with a calibrated probe and judged against the limit for the type of food."},
    {"step": "Cooling", "hazard": "Spores and bacteria grow while cooked food cools", "kind": "Biological", "significant": True,
     "control": "Cooling log with a temperature and a time limit at each stage; failures are acted on and recorded."},
    {"step": "Reheating", "hazard": "Pathogens survive if food is not reheated through", "kind": "Biological", "significant": True,
     "control": "Core temperature after reheating measured against the limit."},
    {"step": "Hot holding", "hazard": "Bacteria grow if hot food falls below the holding temperature", "kind": "Biological", "significant": True,
     "control": "Holding temperature checked at regular intervals against the limit."},
    {"step": "Cleaning and sanitising", "hazard": "Surviving bacteria on surfaces and equipment; chemical residue", "kind": "Chemical", "significant": False,
     "control": "Sanitiser strength and dishwasher temperatures checked; cleaning checklists completed and approved."},
    {"step": "Allergens", "hazard": "Allergen cross-contact or wrong information to the guest", "kind": "Allergen", "significant": True,
     "control": "Separate utensils and storage, clear labelling and staff training. Add the kitchen's own allergen controls here."},
]


# One flow per kind of food, every step from the supplier to the guest; the control tags match the cooling and hot-holding templates and are edited on the plan.
_PROCESSES = {
    "Hot food": ["Supplier approval and ordering", "Receiving: temperature, packaging, labels and dates checked", "Accept, or reject and return non-conforming goods",
                 "Label with received date and lot", "Dry, chilled or frozen storage", "Issue from store, oldest stock first", "Defrosting", "Washing fruit and vegetables",
                 "Preparing raw meat, poultry and fish in a separate area", "Portioning, marinating and assembly", "Cooking", "Core temperature check after cooking", "Hot holding",
                 "Plating and service", "Transport to other outlets or events", "Cooling of leftovers", "Storing cooked food chilled, labelled and dated", "Reheating"],
    "Cold food and salads": ["Supplier approval and ordering", "Receiving chilled food and produce: temperature, condition and dates", "Label with received date and lot", "Chilled storage",
                             "Washing and sanitising fruit and vegetables", "Cutting and preparing ready-to-eat food on clean, separate boards", "Dressing, mixing and assembly",
                             "Portioning and labelling with the use-by date", "Cold holding", "Cold display and service", "Discarding food at the end of its shelf life"],
    "Stocks, soups and sauces": ["Supplier approval and ordering", "Receiving ingredients: temperature, packaging and dates", "Storage", "Preparing bones, meat and vegetables",
                                 "Cooking and simmering", "Skimming and straining", "Cooling", "Storing chilled, labelled and dated", "Reheating to a rolling boil", "Hot holding",
                                 "Service"],
    "Sushi and raw fish": ["Approved fish supplier; parasite-control certificate or freezing record checked", "Receiving fish: temperature, smell and appearance",
                           "Chilled storage, raw fish kept apart", "Cooking sushi rice", "Adding vinegar to the rice and holding it", "Preparing raw fish on its own board and knife",
                           "Rolling and assembly", "Cold holding", "Display and service within the time allowed", "Discarding what is left at the end of service"],
    "Cleaning, hygiene and waste (all areas)": ["Staff hygiene, handwashing and health checks", "Cleaning and sanitising surfaces and equipment", "Dishwashing and glass washing",
                                                "Leftovers and food waste", "Pest control and waste removal"],
}
STARTER_PROCESSES = [{"name": name, "steps": [{"name": n, "control": "CCP" if n.startswith("Cooling") or n == "Hot holding" else ""} for n in steps]} for name, steps in _PROCESSES.items()]


def default_content() -> dict:
    return {"owner": "", "team": "", "scope": "", "products": "", "review": REVIEW, "processes": [{"name": p["name"], "steps": [dict(s) for s in p["steps"]]} for p in STARTER_PROCESSES],
            "hazards": [{**h, "process": ""} for h in STARTER_HAZARDS], "revisions": []}


def _upgraded(content: dict) -> dict:
    """A plan saved with one flow becomes one process, so nothing written is lost when the plan grew separate flows per kind of food."""
    merged = {**default_content(), **content}
    if "processes" not in content and content.get("flow"):
        merged["processes"] = [{"name": "All food", "steps": content["flow"]}]
    merged.pop("flow", None)
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
    flows = [{"title": p["name"] if i == 0 else f"Process flow: {p['name']}", "meta": [], "columns": [("name", "Step")], "rows": [], "totals": [], "flow": p["steps"],
              "empty": "No process steps written yet."} for i, p in enumerate(content["processes"] if content["processes"] else [{"name": "Process", "steps": []}])]
    hazards = {"title": "Hazard analysis", "meta": [], "columns": [("process", "Applies to"), ("step", "Process step"), ("hazard", "Hazard"), ("kind", "Type"), ("significant", "Significant"), ("control", "Control measure")],
               "rows": [{**h, "process": h.get("process") or "All processes", "significant": "Yes" if h.get("significant") else "No"} for h in content["hazards"]], "totals": [],
               "empty": "No hazards written yet."}
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
    chapters = [("Plan details", [details]), ("Process flow", flows), ("Hazard analysis", [hazards]), ("Control points and limits", [cp]), ("Corrective action and verification", [corrective, thermometers]),
                ("Revision history", [revisions])]
    groups, contents = [], []
    for number, (title, found) in enumerate(chapters, 1):
        heading = f"{number}. {title}"
        contents.append(heading)
        groups += [{**found[0], "title": f"{heading}: {found[0]['title']}" if found[0]["title"] != title else heading}, *found[1:]]
    label = f"Version {version}"
    return {"kind": "haccp_plan", "title": "HACCP plan", "period": {"from": "", "to": "", "label": label}, "locations": [loc.name for loc in locations],
            "prepared_by": prepared_by, "groups": groups, "contents": contents}
