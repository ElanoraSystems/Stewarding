from sqlalchemy.orm import Session

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
    "approval.checklists": 1,
}


def get_setting(db: Session, key: str):
    row = db.get(Setting, key)
    return row.value["v"] if row else DEFAULTS[key]


def all_settings(db: Session) -> dict:
    return {key: get_setting(db, key) for key in DEFAULTS}
