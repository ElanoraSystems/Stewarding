"""the Back of House Manager may delete a monitoring point or check together with its readings

Revision ID: u5c9e3a7d1b4
Revises: t4b8d2f6a0c3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u5c9e3a7d1b4"
down_revision: Union[str, Sequence[str], None] = "t4b8d2f6a0c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    db = op.get_bind()
    role_id = db.execute(sa.text("SELECT id FROM role WHERE name = 'manager'")).scalar()
    if role_id is not None:
        db.execute(sa.text("INSERT INTO role_permission (role_id, permission) VALUES (:r, 'equipment.delete')"), {"r": role_id})


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM role_permission WHERE permission = 'equipment.delete'"))
