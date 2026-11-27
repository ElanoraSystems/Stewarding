"""Who sees a checklist or records a monitoring log: either can be limited to chosen job titles.

Managers and the people who set checklists or monitoring up always reach everything. Those who approve the work reach what they may decide: where
nobody is named to approve, anyone whose role can approve; where people are named, only them. They cannot approve what they cannot see. Nothing chosen means everyone."""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChecklistTemplate, Equipment, LookupValue, User


def norm_title(title: str | None) -> str:
    """A job title compared without regard to case or extra spaces."""
    return " ".join((title or "").split()).casefold()


def title_of(user: User) -> str:
    return norm_title(user.employee.job_title) if user.employee else ""


def clean_titles(db: Session, names: list[str] | None) -> list[str] | None:
    """The job titles something is limited to, each one checked against the titles set up in Settings; nothing chosen means everyone."""
    chosen = list(dict.fromkeys(" ".join(n.split()) for n in (names or []) if n.strip()))
    if not chosen:
        return None
    known = {norm_title(v): v for v in db.scalars(select(LookupValue.value).where(LookupValue.kind == "job_title"))}
    if any(norm_title(n) not in known for n in chosen):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown job title. Add it in Settings first")
    return list(dict.fromkeys(known[norm_title(n)] for n in chosen))


def allows(visible_to: list[str] | None, user: User) -> bool:
    """True when nothing limits it, or the person's job title is one of those chosen."""
    return not visible_to or title_of(user) in {norm_title(t) for t in visible_to}


def _decides(user: User, approvers: list[int] | None) -> bool:
    from .approvers import may_decide  # approvers imports this module
    return may_decide(user, approvers)


def _has(user: User, *permissions: str) -> bool:
    return any(p.permission in permissions for p in user.role.permissions)


def sees_everything(user: User) -> bool:
    return user.role.tier == "manager" or _has(user, "checklist.configure")


def may_see(user: User, template: ChecklistTemplate) -> bool:
    """Not a checklist someone else is named to approve: holding the approval permission alone no longer shows it."""
    return sees_everything(user) or allows(template.visible_to, user) or (_has(user, "checklist.verify") and _decides(user, template.approvers))


def hidden_templates(db: Session, user: User) -> set[int]:
    """The checklists this person's job title is not allowed to see (none for a manager or someone who sets checklists up)."""
    if sees_everything(user):
        return set()
    return {t.id for t in db.scalars(select(ChecklistTemplate).where(ChecklistTemplate.visible_to.is_not(None))) if not may_see(user, t)}


def may_record_everything(user: User) -> bool:
    return user.role.tier == "manager" or _has(user, "equipment.manage")


def may_record(user: User, eq: Equipment) -> bool:
    """A log limited to certain job titles is recorded only by those; managers and whoever sets monitoring up can always reach it."""
    return may_record_everything(user) or allows(eq.visible_to, user) or (_has(user, "temp.review") and _decides(user, eq.approvers))


def hidden_points(db: Session, user: User) -> set[int]:  # also keeps their readings out of the monitoring log
    """The monitoring points this person's job title is not allowed to record, so their counts and charts leave them out too."""
    if may_record_everything(user):
        return set()
    return {e.id for e in db.scalars(select(Equipment).where(Equipment.visible_to.is_not(None))) if not may_record(user, e)}
