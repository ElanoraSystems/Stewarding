"""an overdue-check alert is a notice, not something to approve

Revision ID: d7f1c3e9a5b6
Revises: c6e0b2d8f4a5
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d7f1c3e9a5b6"
down_revision: Union[str, Sequence[str], None] = "c6e0b2d8f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE notification SET requires_ack = FALSE WHERE kind = 'monitoring_overdue' AND requires_ack")


def downgrade() -> None:
    """The earlier alerts are not made to need approval again."""
