from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def iso(dt: datetime | None) -> str | None:
    """Stored datetimes are naive UTC; clients get an explicit Z."""
    return dt.isoformat() + "Z" if dt else None


def row(obj, *fields: str) -> dict:
    return {f: iso(v) if isinstance(v := getattr(obj, f), datetime) else v for f in fields}


def paginate(db: Session, stmt, page: int = 1, size: int = 25):
    """Returns (total, rows) for one page of `stmt`."""
    size = min(max(size, 1), 200)
    page = max(page, 1)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return total, db.execute(stmt.limit(size).offset((page - 1) * size)).all()
