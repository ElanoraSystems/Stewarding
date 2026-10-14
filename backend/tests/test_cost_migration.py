"""The cost migration gives every existing movement its weighted average cost by replaying the ledger."""
import importlib.util
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (InventoryBalance, InventoryItem, Location, Receipt, ReceiptLine, StockTransaction, Supplier, User)

PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "c9d5f1b3e7a0_weighted_average_cost.py"


def test_replaying_the_old_ledger_gives_every_movement_a_cost_and_each_balance_an_average(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/m.db")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Location(id=1, code="L1", name="One", kind="kitchen", timezone="UTC"), Location(id=2, code="L2", name="Two", kind="kitchen", timezone="UTC")])
        db.add(User(id=1, email="u@example.com", password_hash="x", role_id=1))
        db.flush()
        item = InventoryItem(code="I1", name="Plate", name_key="plate", category_id=1, unit_id=1, min_level=0, unit_cost=Decimal("5.00"))
        db.add(item)
        db.add(Supplier(id=1, name="S", name_key="s"))
        db.flush()
        db.add(Receipt(id=1, doc_type="receipt", supplier_id=1, location_id=1, invoice_number="A", received_at=datetime(2026, 1, 3), received_by=1, status="posted"))
        day = lambda d: datetime(2026, 1, d)  # noqa: E731
        txns = [("opening", 10, day(1)), ("receipt", 10, day(3)), ("issue", -5, day(4)), ("receipt", 5, day(5))]
        made = []
        for kind, qty, when in txns:
            t = StockTransaction(item_id=item.id, location_id=1, txn_type=kind, qty_delta=qty, occurred_at=when, user_id=1)
            db.add(t)
            db.flush()
            made.append(t)
        db.add(StockTransaction(item_id=item.id, location_id=2, txn_type="opening", qty_delta=3, occurred_at=day(1), user_id=1))
        db.add(ReceiptLine(receipt_id=1, item_id=item.id, qty=10, unit_cost=Decimal("5.00"), line_total=Decimal("40.00"), transaction_id=made[1].id))
        db.add(InventoryBalance(item_id=item.id, location_id=1, qty=20))
        db.add(InventoryBalance(item_id=item.id, location_id=2, qty=3))
        db.commit()
    with engine.begin() as conn:
        for table, column in (("stock_transaction", "unit_cost"), ("inventory_balance", "avg_cost"), ("stock_snapshot", "value")):
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        spec = importlib.util.spec_from_file_location("cost_migration", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
        costs = [Decimal(str(c)) for (c,) in conn.execute(text("SELECT unit_cost FROM stock_transaction ORDER BY location_id, occurred_at, id"))]
        averages = {loc: Decimal(str(a)) for loc, a in conn.execute(text("SELECT location_id, avg_cost FROM inventory_balance"))}
    # opening at the item's own cost 5.00; the priced receipt (4.00 a unit) blends to 4.50; the issue takes 4.50; the unpriced receipt is valued at 4.50
    assert costs[:4] == [Decimal("5.0000"), Decimal("4.0000"), Decimal("4.5000"), Decimal("4.5000")]
    assert costs[4] == Decimal("5.0000")
    assert averages == {1: Decimal("4.5000"), 2: Decimal("5.0000")}


def test_the_migration_runs_on_a_database_with_no_stock_at_all(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/empty.db")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column in (("stock_transaction", "unit_cost"), ("inventory_balance", "avg_cost"), ("stock_snapshot", "value")):
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        spec = importlib.util.spec_from_file_location("cost_migration_empty", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
        assert conn.execute(text("SELECT count(*) FROM stock_transaction")).scalar() == 0
