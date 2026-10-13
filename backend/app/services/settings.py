from sqlalchemy import event, select
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


CACHE_KEY = "settings"


def _stored(db: Session) -> dict:
    """Every stored setting, read once per transaction and kept on the session; it is dropped when the transaction ends."""
    cache = db.info.get(CACHE_KEY)
    if cache is None:
        cache = db.info[CACHE_KEY] = {row.key: row.value["v"] for row in db.scalars(select(Setting))}
    return cache


@event.listens_for(Session, "after_transaction_end")
def _forget_after_transaction(session, _transaction):
    session.info.pop(CACHE_KEY, None)


@event.listens_for(Session, "before_flush")
def _forget_when_settings_change(session, _context, _instances):
    if any(isinstance(obj, Setting) for obj in (*session.new, *session.dirty)):
        session.info.pop(CACHE_KEY, None)


def get_setting(db: Session, key: str):
    stored = _stored(db)
    return stored[key] if key in stored else DEFAULTS[key]


def all_settings(db: Session) -> dict:
    return {key: get_setting(db, key) for key in DEFAULTS}
