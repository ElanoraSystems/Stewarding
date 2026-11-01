"""Every approve or reject decision is kept with its comment, so the approvals report can show who decided what and why."""
from sqlalchemy.orm import Session

from ..models import ApprovalRecord, User


def record_decision(db: Session, user: User, subject_type: str, subject_id: int, approved: bool, comment: str | None) -> None:
    db.add(ApprovalRecord(subject_type=subject_type, subject_id=subject_id, decision="approved" if approved else "rejected",
                          decided_by=user.id, reason=(comment or "").strip() or None))
