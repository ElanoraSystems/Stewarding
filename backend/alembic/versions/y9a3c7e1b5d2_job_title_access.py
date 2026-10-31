"""checklists and monitoring points are limited by job title, not by role

Revision ID: y9a3c7e1b5d2
Revises: x8f2b6d0a4e7
"""
from typing import Sequence, Union

from alembic import op

revision: str = "y9a3c7e1b5d2"
down_revision: Union[str, Sequence[str], None] = "x8f2b6d0a4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # the column now holds job titles; any role names saved before would match nobody, so those limits are cleared (everyone sees them again)
    op.execute("UPDATE checklist_template SET visible_to = NULL WHERE visible_to IS NOT NULL")
    op.execute("UPDATE equipment SET visible_to = NULL WHERE visible_to IS NOT NULL")


def downgrade() -> None:
    pass  # role names cannot be recovered from job titles
