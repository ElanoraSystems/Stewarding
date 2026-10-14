"""weighted average cost: the cost of every movement and a running average per item and location

Revision ID: c9d5f1b3e7a0
Revises: b8c4e0a2d6f9
"""
from collections import defaultdict
from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d5f1b3e7a0"
down_revision: Union[str, Sequence[str], None] = "b8c4e0a2d6f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BATCH = 5000
FOUR = Decimal("0.0001")


def upgrade() -> None:
    with op.batch_alter_table("stock_transaction") as batch:
        batch.add_column(sa.Column("unit_cost", sa.Numeric(14, 4)))
    with op.batch_alter_table("inventory_balance") as batch:
        batch.add_column(sa.Column("avg_cost", sa.Numeric(14, 4)))
    with op.batch_alter_table("stock_snapshot") as batch:
        batch.add_column(sa.Column("value", sa.Numeric(16, 4)))
    bind = op.get_bind()
    # month-end copies hold no value yet; the scheduler rebuilds them from the ledger
    bind.execute(sa.text("DELETE FROM stock_snapshot"))
    reference = {i: Decimal(str(c)) for i, c in bind.execute(sa.text("SELECT id, unit_cost FROM inventory_item")) if c is not None}
    priced = {}
    for txn_id, qty, total in bind.execute(sa.text("SELECT transaction_id, qty, line_total FROM receipt_line WHERE line_total IS NOT NULL AND qty > 0")):
        priced[txn_id] = (Decimal(str(total)) / qty).quantize(FOUR)
    qty_now: dict = defaultdict(int)
    avg_now: dict = {}
    updates = []
    rows = bind.execute(sa.text("SELECT id, item_id, location_id, qty_delta FROM stock_transaction ORDER BY item_id, location_id, occurred_at, id"))
    for txn_id, item_id, loc_id, delta in rows:
        key = (item_id, loc_id)
        base = avg_now.get(key, reference.get(item_id))
        if delta > 0:
            cost = priced.get(txn_id, base)
            if cost is not None:
                before = max(qty_now[key], 0)
                avg_now[key] = cost if before == 0 or base is None else ((before * base + delta * cost) / (before + delta)).quantize(FOUR)
        else:
            cost = base
        qty_now[key] += delta
        if cost is not None:
            updates.append({"c": float(cost), "i": txn_id})
        if len(updates) >= BATCH:
            bind.execute(sa.text("UPDATE stock_transaction SET unit_cost = :c WHERE id = :i"), updates)
            updates = []
    if updates:
        bind.execute(sa.text("UPDATE stock_transaction SET unit_cost = :c WHERE id = :i"), updates)
    bind.execute(sa.text("UPDATE inventory_balance SET avg_cost = :c WHERE item_id = :i AND location_id = :l"),
                 [{"c": float(avg), "i": item, "l": loc} for (item, loc), avg in avg_now.items()])


def downgrade() -> None:
    """Costs are dropped; the quantities and the ledger are untouched."""
    with op.batch_alter_table("stock_snapshot") as batch:
        batch.drop_column("value")
    with op.batch_alter_table("inventory_balance") as batch:
        batch.drop_column("avg_cost")
    with op.batch_alter_table("stock_transaction") as batch:
        batch.drop_column("unit_cost")
