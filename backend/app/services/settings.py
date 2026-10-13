from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cache import memo

from ..models import Setting

# Every operational threshold is configurable; these are defaults until a manager changes them.
DEFAULTS: dict[str, int | bool] = {
    "temp.due_grace_minutes": 30,
    "temp.retest_minutes": 15,
    "temp.repeat_failure_count": 3,
    "temp.repeat_failure_days": 7,
    "temp.escalate_after_minutes": 60,
    "reminder.lead_minutes": 30,
    "escalation.supervisor_after_minutes": 30,
    "escalation.manager_after_minutes": 120,
    "breakage.approval_qty": 5,
    "breakage.approval_cost": 100,
    "attendance.missed_checkout_hours": 16,
    "attendance.max_accuracy_m": 100,
    "approval.checklists": 1,
}


def _stored(db: Session) -> dict:
    """Every stored setting, read once per transaction."""
    return memo(db, "settings", lambda: {row.key: row.value["v"] for row in db.scalars(select(Setting))})


def get_setting(db: Session, key: str):
    stored = _stored(db)
    return stored[key] if key in stored else DEFAULTS[key]


def all_settings(db: Session) -> dict:
    return {key: get_setting(db, key) for key in DEFAULTS}
