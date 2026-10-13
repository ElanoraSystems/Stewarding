"""Values worked out once per transaction and kept on the database session.

A copy is dropped when the transaction ends (commit or rollback) and when a flush changes a row it could depend on,
so it can never outlive the data it was built from or leak between requests.
"""
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session

T = TypeVar("T")

KEY = "memo"
# Rows whose change makes a kept copy stale. Names, not classes, to keep this module free of model imports.
WATCHED = {"Setting", "EmployeeLocation", "Employee", "Location", "Shift", "Role", "RolePermission", "User"}


def memo(db: Session, key: object, build: Callable[[], T]) -> T:
    """The value for `key`, built on first use and kept for the rest of the transaction."""
    kept = db.info.setdefault(KEY, {})
    if key not in kept:
        kept[key] = build()
    return kept[key]


@event.listens_for(Session, "after_transaction_end")
def _forget_after_transaction(session, _transaction):
    session.info.pop(KEY, None)


@event.listens_for(Session, "before_flush")
def _forget_when_related_rows_change(session, _context, _instances):
    if any(type(obj).__name__ in WATCHED for obj in (*session.new, *session.dirty, *session.deleted)):
        session.info.pop(KEY, None)
