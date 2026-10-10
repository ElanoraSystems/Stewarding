from sqlalchemy.orm import Session

from .models import AuditLog, User


def audit(db: Session, user: User | None, action: str, entity: str, entity_id: int | None = None,
          before: dict | None = None, after: dict | None = None) -> None:
    """Adds an audit row to the caller's transaction; the caller commits."""
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity=entity,
                    entity_id=entity_id, before=before, after=after))
