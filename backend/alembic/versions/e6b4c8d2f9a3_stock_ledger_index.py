"""composite index for location and time range reads of the stock ledger

Revision ID: e6b4c8d2f9a3
Revises: d5a9b3e7c2f1
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e6b4c8d2f9a3"
down_revision: Union[str, Sequence[str], None] = "d5a9b3e7c2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_stock_transaction_location_time_item", "stock_transaction", ["location_id", "occurred_at", "item_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_transaction_location_time_item", table_name="stock_transaction")
