"""stored search keys so duplicate item names are found by index

Revision ID: a1e7f3c9d5b2
Revises: f7c5d9e3a0b4
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1e7f3c9d5b2"
down_revision: Union[str, Sequence[str], None] = "f7c5d9e3a0b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WORDS = re.compile(r"[a-z0-9]+")


def _stem(word: str) -> str:
    """A very small singular form: glasses to glass, boxes to box, plates to plate."""
    if len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes", "zes")):
        return word[:-2]
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _keys(name: str) -> tuple[str, str]:
    """The same rules as services/similarity, written out here so the migration never changes when the code does."""
    words = WORDS.findall(name.lower())
    return "".join(words), " ".join(sorted({_stem(w) for w in words}))


def upgrade() -> None:
    with op.batch_alter_table("inventory_item") as batch:
        batch.add_column(sa.Column("compact_key", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("token_key", sa.String(200), nullable=False, server_default=""))
    items = sa.table("inventory_item", sa.column("id", sa.Integer), sa.column("name", sa.String),
                     sa.column("compact_key", sa.String), sa.column("token_key", sa.String))
    bind = op.get_bind()
    for item_id, name in bind.execute(sa.select(items.c.id, items.c.name)).all():
        compact, token = _keys(name)
        bind.execute(items.update().where(items.c.id == item_id).values(compact_key=compact, token_key=token))
    op.create_index("ix_inventory_item_compact_key", "inventory_item", ["compact_key"])
    op.create_index("ix_inventory_item_token_key", "inventory_item", ["token_key"])


def downgrade() -> None:
    op.drop_index("ix_inventory_item_token_key", table_name="inventory_item")
    op.drop_index("ix_inventory_item_compact_key", table_name="inventory_item")
    with op.batch_alter_table("inventory_item") as batch:
        batch.drop_column("token_key")
        batch.drop_column("compact_key")
