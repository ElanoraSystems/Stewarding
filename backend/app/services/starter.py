from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChecklistTask, ChecklistTemplate, Shift

# description, requires_verification, priority
DAILY = [
    ("Clean and sanitize kitchen floors", False, "normal"),
    ("Clean drains and remove debris", False, "normal"),
    ("Clean worktables and food preparation surfaces", False, "high"),
    ("Clean and sanitize dishwashing areas", False, "high"),
    ("Clean dishwasher filters", True, "high"),
    ("Clean glasswasher filters", True, "high"),
    ("Check chemical dispensers and detergent levels", False, "high"),
    ("Clean waste bins and surrounding areas", False, "normal"),
    ("Separate and remove waste", False, "normal"),
    ("Clean and organize crockery storage", False, "normal"),
    ("Check smallware storage and return items to designated areas", False, "normal"),
    ("Check for damaged crockery", False, "normal"),
    ("Clean walls and splashbacks where required", False, "normal"),
    ("Verify the stewarding area is ready for the next shift", True, "high"),
]
WEEKLY = [
    ("Deep-clean dishwasher and glasswasher components per manufacturer guidance", True, "high", None),
    ("Deep-clean storage racks and shelving", False, "normal", None),
    ("Inspect drains and grease-trap cleaning records where applicable", True, "high", None),
    ("Clean designated high-level areas", False, "normal", None),
    ("Inspect cleaning tools and replace damaged equipment", False, "normal", None),
    ("Review chemical storage and labels", True, "high", None),
    ("Inspect crockery and smallware storage", False, "normal", None),
    ("Check equipment condition and report defects", False, "normal", None),
    ("Review recurring cleaning issues", True, "normal", "supervisor"),
    ("Complete weekly supervisor inspection", True, "high", "supervisor"),
]


def apply_starter(db: Session, location_id: int) -> int:
    """Adds the starter daily and weekly templates to a location; skips ones that already exist."""
    morning = db.scalar(select(Shift).where(Shift.active.is_(True), Shift.kind == "work").order_by(Shift.start_time))
    added = 0
    for name, frequency in (("Daily Stewarding Checklist", "daily"), ("Weekly Stewarding Checklist", "weekly")):
        if db.scalar(select(ChecklistTemplate.id).where(ChecklistTemplate.location_id == location_id,
                                                        ChecklistTemplate.name == name)):
            continue
        template = ChecklistTemplate(name=name, category="Cleaning", location_id=location_id, frequency=frequency)
        db.add(template)
        db.flush()
        if frequency == "daily":
            for desc, verify, priority in DAILY:
                db.add(ChecklistTask(template_id=template.id, description=desc, requires_verification=verify,
                                     priority=priority, shift_id=morning.id if morning else None,
                                     deadline_time=time(13, 30), assigned_role="steward"))
                added += 1
        else:
            for desc, verify, priority, role in WEEKLY:
                db.add(ChecklistTask(template_id=template.id, description=desc, requires_verification=verify,
                                     priority=priority, weekdays="0", deadline_time=time(17, 0),
                                     assigned_role=role or "steward", mandatory_for_checkout=False))
                added += 1
    return added
