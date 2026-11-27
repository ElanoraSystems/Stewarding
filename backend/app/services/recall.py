"""Lot recall trace: where a lot came from and everywhere it went, as the tables of a printable record."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (CorrectiveAction, Equipment, FoodItem, Location, Lot, LotEvent, Receipt, ReceiptLine, ReadingLot, Supplier,
                      TemperatureReading)
from .monitoring import describe
from .reference import user_names
from .traceability import CONDITIONS, balance, descendants, ancestors

MAX_LOTS = 100
EVENT_TITLES = {"split": "Split", "thaw": "Thawed", "status": "Status changed"}


def _local(moment: datetime | None, tz: str) -> str:
    return timeutil.to_local(moment, tz).strftime("%d %b %Y %H:%M") if moment else ""


def _amount(qty: Decimal | float | None, unit: str | None) -> str:
    return "" if qty is None else f"{Decimal(str(qty)).normalize():f} {unit or ''}".strip()


def find_lots(db: Session, locations: list[Location], code: str | None, supplier_id: int | None, day_from: date, day_to: date) -> list[Lot]:
    """The lots to trace: the one with this code, or every delivery from a supplier received in the period."""
    ids = [loc.id for loc in locations]
    if code and code.strip():
        lot = db.scalar(select(Lot).where(func.upper(Lot.code) == code.strip().upper(), Lot.location_id.in_(ids)))
        if lot is None:
            raise ValueError(f"No lot with the code {code.strip()} was found at these locations")
        return [lot]
    if supplier_id is None:
        raise ValueError("Enter a lot code, or choose a supplier to trace all of their deliveries in the period")
    window = or_(*[and_(Lot.location_id == loc.id, Lot.created_at >= timeutil.local_to_utc(day_from, time(0, 0), loc.timezone),
                        Lot.created_at < timeutil.local_to_utc(day_to + timedelta(days=1), time(0, 0), loc.timezone)) for loc in locations])  # the days, in each place's own time
    lots = list(db.scalars(select(Lot).where(Lot.kind == "received", Lot.supplier_id == supplier_id, window).order_by(Lot.created_at, Lot.id).limit(MAX_LOTS + 1))) if locations else []
    if len(lots) > MAX_LOTS:
        raise ValueError(f"More than {MAX_LOTS} deliveries match. Choose a shorter period")
    return lots


def _summary(db: Session, lot: Lot, forward: list[Lot]) -> dict:
    """Quantities in the lot's own unit; blank when it has no quantity or unit."""
    bal = balance(db, lot)
    if bal is None:
        return {"received": "", "used": "", "waste": "", "remaining": "", "discarded": ""}
    unit = lot.unit
    # a discarded lot loses what was left of it; a discarded portion lot loses its whole size (never counted twice under a discarded parent)
    discarded = Decimal(str(bal["left"])) if lot.status == "discarded" else Decimal(0)
    for x in forward:
        if x.status == "discarded" and x.qty is not None and (x.unit or "").lower() == (unit or "").lower():
            discarded += x.qty
    left = Decimal(str(bal["left"])) if lot.status in ("active", "on_hold") else Decimal(0)
    return {"received": _amount(bal["qty"], unit), "used": _amount(bal["portioned"], unit), "waste": _amount(bal["waste"], unit),
            "remaining": _amount(left, unit), "discarded": _amount(discarded, unit)}


def _readings(db: Session, lots: dict[int, Lot], scope_ids: list[int]) -> list[tuple[TemperatureReading, Lot]]:
    """Readings that named any of these lots, plus free-text references that match a lot code exactly."""
    out = {r.id: (r, lots[lot_id]) for r, lot_id in db.execute(
        select(TemperatureReading, ReadingLot.lot_id).join(ReadingLot, ReadingLot.reading_id == TemperatureReading.id).where(ReadingLot.lot_id.in_(list(lots))))}
    by_code = {lot.code.upper(): lot for lot in lots.values()}
    for r in db.scalars(select(TemperatureReading).where(func.upper(func.trim(TemperatureReading.reference)).in_(list(by_code)), TemperatureReading.location_id.in_(scope_ids))):
        out.setdefault(r.id, (r, by_code[r.reference.strip().upper()]))
    return sorted(out.values(), key=lambda pair: (pair[0].recorded_at, pair[0].id))


def lot_groups(db: Session, lot: Lot, scope: set[int] | None) -> tuple[list[dict], dict]:
    """The tables for one lot, and its summary figures."""
    names = user_names(db)
    zones = dict(db.execute(select(Location.id, Location.timezone)).all())
    items = dict(db.execute(select(FoodItem.id, FoodItem.name)).all())
    suppliers = dict(db.execute(select(Supplier.id, Supplier.name)).all())

    def seen(x: Lot) -> bool:  # a lot at a place the person does not work is left out
        return scope is None or x.location_id in scope
    back = [x for x in ancestors(db, lot.id) if seen(x)]
    forward = [x for x in descendants(db, lot.id) if seen(x)]
    root = back[0] if back else lot
    family = [*back, lot, *forward]
    by_id = {x.id: x for x in family}
    summary = _summary(db, lot, forward)

    def lot_row(x: Lot) -> dict:
        z = zones[x.location_id]
        return {"lot": x.code, "type": "Portions" if x.kind == "portion" else "Delivery", "food": items.get(x.food_item_id, ""), "supplier": suppliers.get(x.supplier_id, ""),
                "supplier_lot": x.supplier_lot or "", "received": _local(x.created_at, z), "quantity": _amount(x.qty, x.unit),
                "expiry": x.expiry_on.strftime("%d %b %Y") if x.expiry_on else "", "use_by": _local(x.use_by, z), "stored": CONDITIONS[x.condition],
                "arrival_temp": "" if x.temp_c is None else f"{x.temp_c:f} C", "by": names.get(x.created_by, ""), "status": x.status.replace("_", " ").capitalize()}

    origin_columns = [("lot", "Lot"), ("type", "Type"), ("food", "Food"), ("supplier", "Supplier"), ("supplier_lot", "Supplier lot"), ("received", "Received"),
                      ("quantity", "Quantity"), ("expiry", "Supplier expiry"), ("use_by", "Use by"), ("stored", "Stored as"), ("arrival_temp", "Arrival temperature"),
                      ("by", "Received by"), ("status", "Status")]
    summary_group = {"title": f"Lot {lot.code} - summary", "meta": [("Lot", lot.code), ("Food", items.get(lot.food_item_id, ""))],
                     "columns": [("received", "Received"), ("used", "Made into portions"), ("waste", "Trim and waste"), ("remaining", "Remaining"), ("discarded", "Discarded"),
                                 ("failed", "Failed checks")], "rows": [], "totals": []}
    groups = [summary_group, {"title": f"Lot {lot.code} - where it came from", "meta": [], "columns": origin_columns, "rows": [lot_row(x) for x in [*back, lot]], "totals": []}]

    # lots do not carry a receipt number, so the supplier's documents at the same place that day are listed for the person to match
    docs = []
    if root.supplier_id is not None:
        day = timeutil.to_local(root.created_at, zones[root.location_id]).date()
        for doc in db.scalars(select(Receipt).where(Receipt.supplier_id == root.supplier_id, Receipt.location_id == root.location_id, Receipt.doc_type == "receipt",
                                                    func.coalesce(Receipt.received_on, func.date(Receipt.received_at)) == day).order_by(Receipt.id)):
            lines = db.scalar(select(func.count()).select_from(ReceiptLine).where(ReceiptLine.receipt_id == doc.id)) or 0
            docs.append({"invoice": doc.invoice_number, "invoice_date": doc.invoice_date.strftime("%d %b %Y") if doc.invoice_date else "",
                         "received_on": (doc.received_on or timeutil.to_local(doc.received_at, zones[root.location_id]).date()).strftime("%d %b %Y"), "lines": lines,
                         "total": "" if doc.total is None else f"{doc.total:.3f}", "by": names.get(doc.received_by, ""), "status": "Void" if doc.status == "void" else "Posted"})
    groups.append({"title": "Delivery documents from this supplier that day (a lot is not tied to one invoice: match by the supplier lot above)", "meta": [],
                   "columns": [("invoice", "Invoice"), ("invoice_date", "Invoice date"), ("received_on", "Received on"), ("lines", "Lines"), ("total", "Total"), ("by", "Received by"),
                               ("status", "Status")], "rows": docs, "totals": [], "empty": "No receiving document from this supplier was entered for that day"})

    history = [{"_at": x.created_at, "when": _local(x.created_at, zones[x.location_id]), "lot": x.code, "what": "Received" if x.kind == "received" else "Made into portions",
                "detail": (f"{x.pack_count} x {x.pack_description}, " if x.pack_count and x.pack_description else "") + _amount(x.qty, x.unit), "by": names.get(x.created_by, "")}
               for x in [lot, *forward]]
    for e in db.scalars(select(LotEvent).where(LotEvent.lot_id.in_([x.id for x in [lot, *forward]])).order_by(LotEvent.id)):
        history.append({"_at": e.at, "when": _local(e.at, zones[by_id[e.lot_id].location_id]), "lot": by_id[e.lot_id].code, "what": EVENT_TITLES.get(e.kind, e.kind.capitalize()),
                        "detail": e.detail, "by": names.get(e.user_id, "")})
    history.sort(key=lambda h: (h["_at"], h["what"] != "Received"))
    groups.append({"title": "Where it went - portions, thawing, holds and discards", "meta": [], "columns": [("when", "When"), ("lot", "Lot"), ("what", "What happened"), ("detail", "Detail"), ("by", "By")],
                   "rows": [{k: v for k, v in h.items() if k != "_at"} for h in history], "totals": [("Portion lots", len(forward))]})
    groups.append({"title": "Stock movements", "meta": [], "columns": [("note", "Note")], "totals": [],
                   "rows": [{"note": "Stock transfers and issues are recorded by inventory item, not by lot, so they cannot be traced to this lot. See the Stock Issues and Movements record for the same dates."}]})

    pairs = _readings(db, by_id, list(zones))
    actions: dict[int, list[CorrectiveAction]] = {}
    for a in db.scalars(select(CorrectiveAction).where(CorrectiveAction.reading_id.in_([r.id for r, _ in pairs] or [0])).order_by(CorrectiveAction.id)):
        actions.setdefault(a.reading_id, []).append(a)
    equipment = dict(db.execute(select(Equipment.id, Equipment.name)).all())
    rows, failed = [], 0
    for r, named in pairs:
        rejected = r.rejected_at is not None
        failed += 0 if (r.passed or rejected) else 1
        taken = "; ".join(f"{a.action} ({names.get(a.taken_by, '')}, {_local(a.taken_at, zones[r.location_id])}, {a.status})" for a in actions.get(r.id, []))
        rows.append({"when": _local(r.recorded_at, zones[r.location_id]), "lot": named.code, "point": equipment.get(r.equipment_id, ""), "check": r.stage,
                     "recorded": describe(r), "result": "Rejected" if rejected else "PASS" if r.passed else "FAIL", "by": names.get(r.recorded_by, ""), "action": taken,
                     "_tone": {"result": "ok" if r.passed and not rejected else "bad"}})
    groups.append({"title": "Monitoring checks that named this lot or its portions", "meta": [],
                   "columns": [("when", "When"), ("lot", "Lot"), ("point", "Monitoring point"), ("check", "Check"), ("recorded", "Recorded"), ("result", "Result"), ("by", "By"),
                               ("action", "Corrective action")], "rows": rows, "totals": [("Checks", len(rows)), ("Failed", failed)],
                   "empty": "No monitoring check has named this lot"})
    summary["failed"] = failed
    summary_group["rows"] = [summary]
    summary_group["totals"] = [("Failed checks", failed)]
    return groups, summary


def recall_groups(db: Session, locations: list[Location], scope: set[int] | None, code: str | None, supplier_id: int | None, day_from: date, day_to: date) -> list[dict]:
    lots = find_lots(db, locations, code, supplier_id, day_from, day_to)
    if len(lots) == 1 and code and code.strip():
        return lot_groups(db, lots[0], scope)[0]
    items = dict(db.execute(select(FoodItem.id, FoodItem.name)).all())
    zones = dict(db.execute(select(Location.id, Location.timezone)).all())
    overview = {"title": "Deliveries traced", "meta": [], "columns": [("lot", "Lot"), ("food", "Food"), ("received", "Received"), ("quantity", "Quantity"), ("used", "Made into portions"),
                                                                       ("remaining", "Remaining"), ("discarded", "Discarded"), ("failed", "Failed checks")],
                "rows": [], "totals": [("Lots", len(lots))], "empty": "No deliveries from this supplier in the period"}
    groups = []
    for lot in lots:
        tables, s = lot_groups(db, lot, scope)
        overview["rows"].append({"lot": lot.code, "food": items.get(lot.food_item_id, ""), "received": _local(lot.created_at, zones[lot.location_id]), "quantity": s["received"],
                                 "used": s["used"], "remaining": s["remaining"], "discarded": s["discarded"], "failed": s["failed"]})
        groups += [{**g, "title": g["title"] if lot.code in g["title"] else f"{lot.code}: {g['title']}"} for g in tables]
    return [overview, *groups]
