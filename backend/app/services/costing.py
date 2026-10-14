"""Stock cost over a period at weighted average cost: opening value, purchases, closing value and what that means was consumed."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import InventoryBalance, InventoryItem, StockTransaction


def cost_report(db: Session, location_id: int, start: datetime, end: datetime) -> dict:
    """Per item and in total for [start, end): cost consumed = opening + purchases + returns + transfers in - transfers out - closing."""
    inside = case((StockTransaction.occurred_at >= start, 1), else_=0)
    worth = func.sum(StockTransaction.qty_delta * func.coalesce(StockTransaction.unit_cost, 0))
    sums = db.execute(
        select(StockTransaction.item_id, StockTransaction.txn_type, inside, func.sum(StockTransaction.qty_delta), worth)
        .where(StockTransaction.location_id == location_id, StockTransaction.occurred_at < end)
        .group_by(StockTransaction.item_id, StockTransaction.txn_type, inside)).all()
    qty_before: dict[int, int] = defaultdict(int)
    value_before: dict[int, Decimal] = defaultdict(Decimal)
    flow: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    qty_flow: dict[int, int] = defaultdict(int)
    loaded: dict[int, int] = defaultdict(int)  # opening stock loaded inside the period counts as opening
    for item_id, txn_type, in_window, qty, value in sums:
        value = Decimal(str(value or 0))
        if in_window:
            flow[item_id][txn_type] += value
            qty_flow[item_id] += qty
            if txn_type == "opening":
                loaded[item_id] += qty
        else:
            qty_before[item_id] += qty
            value_before[item_id] += value
    ids = set(qty_before) | set(flow)
    names = {i.id: (i.code, i.name) for i in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(ids)))} if ids else {}
    averages = dict(db.execute(select(InventoryBalance.item_id, InventoryBalance.avg_cost).where(InventoryBalance.location_id == location_id)).all())
    rows, totals = [], defaultdict(Decimal)
    for item_id in sorted(ids, key=lambda i: names[i][0]):
        f = flow[item_id]
        opening = value_before[item_id] + f["opening"]
        closing = value_before[item_id] + sum(f.values())
        consumed = opening + f["receipt"] + f["return"] + f["transfer_in"] + f["transfer_out"] - closing
        row = {"item_id": item_id, "code": names[item_id][0], "name": names[item_id][1],
               "opening_qty": qty_before[item_id] + loaded[item_id], "closing_qty": qty_before[item_id] + qty_flow[item_id],
               "average_cost": float(averages[item_id]) if averages.get(item_id) is not None else None,
               "opening_value": opening, "purchases": f["receipt"], "returns": f["return"], "transfers_in": f["transfer_in"],
               "transfers_out": -f["transfer_out"], "closing_value": closing, "cost_consumed": consumed,
               "issued": -f["issue"], "breakage_damage": -(f["breakage"] + f["damage"]), "count_adjustments": f["adjustment"]}
        for key in ("opening_value", "purchases", "returns", "transfers_in", "transfers_out", "closing_value", "cost_consumed", "issued",
                    "breakage_damage", "count_adjustments"):
            totals[key] += row[key]
            row[key] = round(float(row[key]), 2)
        rows.append(row)
    return {"rows": rows, "totals": {k: round(float(v), 2) for k, v in totals.items()}}

