"""The words typed in a document search, matched against the invoice, the note, the supplier and the items on the document."""
from sqlalchemy import Select, or_, select

from ..models import InventoryItem, Receipt, ReceiptLine, Supplier


def apply_search(stmt: Select, q: str | None) -> Select:
    """Every word must match something on the document: its invoice number, note, supplier, or the name or code of an item on it."""
    for word in (q or "").split():
        like = f"%{word}%"
        on_lines = select(ReceiptLine.receipt_id).join(InventoryItem, InventoryItem.id == ReceiptLine.item_id).where(
            or_(InventoryItem.name.ilike(like), InventoryItem.code.ilike(like)))
        by_supplier = select(Supplier.id).where(Supplier.name.ilike(like))
        stmt = stmt.where(or_(Receipt.invoice_number.ilike(like), Receipt.note.ilike(like), Receipt.supplier_id.in_(by_supplier), Receipt.id.in_(on_lines)))
    return stmt
