"""A read-only change history for a checklist or a monitoring point, built from the audit log: who changed what, when, and from what to what."""
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models import AuditLog
from .reference import user_names

WHAT = {
    "checklist.template_create": "Created the checklist", "checklist.template_update": "Changed the checklist", "checklist.task_create": "Added a task",
    "checklist.task_update": "Changed a task", "checklist.task_deactivate": "Removed a task",
    "equipment.create": "Created the monitoring point", "equipment.update": "Changed the monitoring point", "equipment.delete": "Deleted the monitoring point",
    "equipment.schedule_create": "Added a check", "equipment.schedule_update": "Changed a check", "equipment.schedule_active": "Switched a check on or off",
    "equipment.schedule_delete": "Deleted a check",
}
SUBJECT_KEYS = ("description", "stage")  # what a task or a check is called
SKIP = {"id", "template_id", "equipment_id"}
LIMIT = 200


def _show(value) -> str:
    if value is None or value == "None" or value == "":
        return "(none)"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) or "(none)"
    text = str(value)
    return text if len(text) <= 160 else text[:157] + "..."


def _same(a, b) -> bool:
    blank = lambda v: v in (None, "", "None", [], "[]")  # noqa: E731
    return (blank(a) and blank(b)) or str(a) == str(b)


def changes(before: dict | None, after: dict | None) -> list[dict]:
    """Field by field what changed; for a new item, its filled-in fields; for a removed one, what it had."""
    before, after = before or {}, after or {}
    out = []
    for key in [*after, *(k for k in before if k not in after)]:
        if key in SKIP:
            continue
        old, new = before.get(key), after.get(key)
        if before and after and _same(old, new):
            continue
        if not before and _same(new, None) or not after and _same(old, None):
            continue  # nothing there to show
        out.append({"field": key.replace("_", " ").capitalize(), "from": None if not before else _show(old), "to": None if not after else _show(new)})
    return out


def history(db: Session, subjects: list[tuple[str, set[int]]]) -> list[dict]:
    """Audit rows for the given (entity, ids) pairs, newest first."""
    match = [and_(AuditLog.entity == entity, AuditLog.entity_id.in_(ids)) for entity, ids in subjects if ids]
    if not match:
        return []
    names, out = user_names(db), []
    for row in db.scalars(select(AuditLog).where(or_(*match)).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(LIMIT)):
        data = row.after or row.before or {}
        subject = next((str(data[k]) for k in SUBJECT_KEYS if data.get(k)), "")
        out.append({"when": row.created_at.isoformat() + "Z", "by": names.get(row.user_id, "System"), "what": WHAT.get(row.action, row.action),
                    "subject": subject if row.entity in ("checklist_task", "equipment_schedule") else "", "changes": changes(row.before, row.after)})
    return out
