"""Printable record documents: one titled table per location and monitoring point or checklist, for audits and month end."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (ChecklistInstance, ChecklistTask, ChecklistTemplate, CorrectiveAction, Employee, Equipment,
                      InventoryCategory, InventoryItem, Location, Receipt, ReceiptLine, StockTransaction, Supplier,
                      TemperatureReading)
from . import metrics
from .monitoring import describe
from .reference import user_names

KINDS = {"monitoring": "Monitoring Record", "checklists": "Checklist Record", "checklist_chart": "Checklist Completion Chart",
         "attendance": "Attendance Record", "attendance_sheet": "Employee Attendance Sheet", "receipts": "Receipts and Invoices", "movements": "Stock Issues and Movements"}
MAX_DAYS = 366
CHART_DAYS = 31
MOVEMENTS = {"receipts": ("receipt",), "issues": ("issue",), "returns": ("return",), "transfers": ("transfer_in", "transfer_out"),
             "breakage": ("damage", "breakage"), "adjustments": ("adjustment",), "opening": ("opening",)}


@dataclass
class Filters:
    location_id: int | None = None
    equipment_id: int | None = None
    employee_id: int | None = None
    supplier_id: int | None = None
    item_id: int | None = None
    movement: str | None = None
    frequency: str | None = None


def _local(dt: datetime | None, tz: str) -> str:
    return timeutil.to_local(dt, tz).strftime("%d %b %Y %H:%M") if dt else ""


def _limits(reading: TemperatureReading) -> str:
    if reading.value_type == "yes_no":
        return "Must be Yes"
    if reading.value_type in ("text", "choice"):
        return "Choice" if reading.value_type == "choice" else "Written answer"
    low = "-" if reading.min_limit is None else f"{reading.min_limit.normalize():f}"
    high = "-" if reading.max_limit is None else f"{reading.max_limit.normalize():f}"
    return f"{low} to {high} {reading.unit or ''}".strip()


def _bounds(day_from: date, day_to: date, tz: str) -> tuple[datetime, datetime]:
    return (timeutil.local_to_utc(day_from, time(0, 0), tz), timeutil.local_to_utc(day_to + timedelta(days=1), time(0, 0), tz))


def _names(db: Session) -> dict[int, str]:
    return user_names(db)


def _locations(db: Session, scope: set[int] | None, location_id: int | None) -> list[Location]:
    stmt = select(Location).where(Location.active.is_(True))
    if location_id is not None:
        stmt = stmt.where(Location.id == location_id)
    elif scope is not None:
        stmt = stmt.where(Location.id.in_(scope))
    return list(db.scalars(stmt.order_by(Location.name)))


def _monitoring_groups(db: Session, locations: list[Location], day_from: date, day_to: date, equipment_id: int | None) -> list[dict]:
    names = _names(db)
    groups = []
    for loc in locations:
        start, end = _bounds(day_from, day_to, loc.timezone)
        stmt = select(Equipment).where(Equipment.location_id == loc.id)
        if equipment_id is not None:
            stmt = stmt.where(Equipment.id == equipment_id)
        for eq in db.scalars(stmt.order_by(Equipment.code)):
            readings = list(db.scalars(select(TemperatureReading).where(
                TemperatureReading.equipment_id == eq.id, TemperatureReading.recorded_at >= start,
                TemperatureReading.recorded_at < end).order_by(TemperatureReading.recorded_at)))
            if not readings:
                continue
            actions = {a.reading_id: a for a in db.scalars(select(CorrectiveAction).where(
                CorrectiveAction.reading_id.in_([r.id for r in readings])))}
            rows = []
            for r in readings:
                a = actions.get(r.id)
                taken = f"{a.action} ({names.get(a.taken_by, '')}, {a.status.replace('_', ' ')})" if a and a.action else (
                    a.status.replace("_", " ") if a else "")
                when = _local(r.recorded_at, loc.timezone)
                rows.append({
                    "date": when[:11], "time": when[12:], "check": r.stage[:1].upper() + r.stage[1:].replace("_", " "), "measure": r.parameter,
                    "value": describe(r), "limits": _limits(r),
                    "result": "Pass" if r.passed else "FAIL", "reference": r.reference or "",
                    "recorded_by": names.get(r.recorded_by, ""),
                    "approved_by": f"{names.get(r.reviewed_by, '')} {_local(r.reviewed_at, loc.timezone)}".strip() if r.reviewed_at else "Awaiting approval",
                    "corrective_action": taken})
            failed = sum(1 for r in readings if not r.passed)
            groups.append({
                "title": f"{loc.name} - {eq.name} ({eq.code})",
                "meta": [("Location", loc.name), ("Monitoring point", f"{eq.name} ({eq.code})"), ("Type", eq.kind)],
                "columns": [("date", "Date"), ("time", "Time"), ("check", "Check"), ("measure", "Measure"), ("value", "Value"),
                            ("limits", "Limits"), ("result", "Result"), ("reference", "Batch / lot"), ("recorded_by", "Recorded by"),
                            ("approved_by", "Approved by"), ("corrective_action", "Corrective action")],
                "rows": rows,
                "totals": [("Checks recorded", len(readings)), ("Passed", len(readings) - failed), ("Failed", failed),
                           ("Awaiting approval", sum(1 for r in readings if not r.reviewed_at))]})
    return groups


def _checklist_groups(db: Session, locations: list[Location], day_from: date, day_to: date,
                      frequency: str | None = None, employee_id: int | None = None) -> list[dict]:
    names = _names(db)
    groups = []
    for loc in locations:
        rows_by_template: dict[str, list] = {}
        stmt = (select(ChecklistInstance, ChecklistTask, ChecklistTemplate)
                .join(ChecklistTask, ChecklistTask.id == ChecklistInstance.task_id)
                .join(ChecklistTemplate, ChecklistTemplate.id == ChecklistTask.template_id)
                .where(ChecklistInstance.location_id == loc.id, ChecklistInstance.local_date >= day_from,
                       ChecklistInstance.local_date <= day_to)
                .order_by(ChecklistInstance.local_date, ChecklistTemplate.name, ChecklistTask.id))
        if frequency:
            stmt = stmt.where(ChecklistTemplate.frequency == frequency)
        if employee_id is not None:
            emp_user = db.scalar(select(Employee.user_id).where(Employee.id == employee_id))
            stmt = stmt.where((ChecklistInstance.assigned_employee_id == employee_id) | (ChecklistInstance.completed_by == (emp_user or -1)))
        for inst, task, template in db.execute(stmt):
            rows_by_template.setdefault(f"{template.name} ({template.frequency})", []).append({
                "date": inst.local_date.strftime("%d %b %Y"), "task": task.description, "status": inst.status.replace("_", " "),
                "completed_by": names.get(inst.completed_by, ""), "completed_at": _local(inst.completed_at, loc.timezone),
                "reading": "" if inst.reading is None else f"{inst.reading.normalize():f}",
                "comment": inst.comment or inst.waive_reason or "",
                "verified_by": names.get(inst.verified_by, ""), "verified_at": _local(inst.verified_at, loc.timezone)})
        for title, rows in rows_by_template.items():
            counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("verified", "pending verification", "completed", "failed")}
            columns = [("date", "Date"), ("task", "Task"), ("status", "Status"), ("completed_by", "Completed by"),
                       ("completed_at", "Completed at"), ("reading", "Reading"), ("comment", "Comment"),
                       ("verified_by", "Approved by"), ("verified_at", "Approved at")]
            if not any(r["reading"] for r in rows):
                columns = [c for c in columns if c[0] != "reading"]  # only tasks that ask for a measurement have one
            groups.append({
                "title": f"{loc.name} - {title}",
                "meta": [("Location", loc.name), ("Checklist", title)],
                "columns": columns,
                "rows": rows,
                "totals": [("Tasks", len(rows)), ("Approved", counts["verified"]), ("Awaiting approval", counts["pending verification"]),
                           ("Rejected", counts["failed"])]})
    return groups


def _initials(name: str | None, legend: dict[str, str]) -> str:
    if not name:
        return ""
    base = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    code, n = base, 2
    while legend.get(code, name) != name:
        code, n = f"{base}{n}", n + 1
    legend[code] = name
    return code


CHART_KEY = "Key: tick = done and approved, amber dotted tick = done, awaiting approval, cross = not done or rejected, W = waived, - = not due"


def _chart_groups(db: Session, now: datetime, scope, f: Filters, day_from: date, day_to: date) -> list[dict]:
    if (day_to - day_from).days >= CHART_DAYS:
        raise ValueError(f"The completion chart covers at most {CHART_DAYS} days; use the checklist record for longer periods")
    names = _names(db)
    days = list(metrics.daterange(day_from, day_to))
    groups = []
    for win in metrics.windows(db, now, scope, f.location_id, day_from, day_to):
        stats = metrics.checklist_stats(db, win, now, f.employee_id, f.frequency)
        by_template: dict[str, dict[tuple[int, str], dict]] = {}
        exceptions: list[dict] = []
        for inst, task, tpl, state in stats["rows"]:
            title = f"{tpl.name} ({tpl.frequency})"
            row = by_template.setdefault(title, {}).setdefault((task.id, task.description), {})
            row.setdefault(inst.local_date, []).append((inst, state))
            if state in ("failed", "overdue", "waived"):
                exceptions.append({"date": inst.local_date.strftime("%d %b %Y"), "task": task.description,
                                   "status": {"failed": "Rejected", "overdue": "Not done", "waived": "Waived"}[state],
                                   "completed_by": names.get(inst.completed_by, ""), "approved_by": names.get(inst.verified_by, ""),
                                   "reason": inst.comment or inst.waive_reason or ""})
        for title, tasks in by_template.items():
            legend: dict[str, str] = {}
            rows, done, expected = [], 0, 0
            for (_, description), by_day in tasks.items():
                row = {"task": description}
                for i, day in enumerate(days):
                    items = by_day.get(day)
                    if not items:
                        row[f"d{i}"] = {"s": "na"}
                        continue
                    states = {state for _, state in items}
                    symbol = ("fail" if states & {"failed", "overdue"} else "pending" if "pending_verification" in states
                              else "waived" if states == {"waived"} else "ok" if states & {"verified", "completed"} else "na")
                    first = next((inst for inst, _ in items if inst.completed_by), items[0][0])
                    row[f"d{i}"] = {"s": symbol, "by": _initials(names.get(first.completed_by), legend),
                                    "ver": _initials(names.get(first.verified_by), legend)}
                    if symbol != "na" and symbol != "waived":
                        expected += 1
                        done += symbol in ("ok", "pending")
                rows.append(row)
            groups.append({
                "title": f"{win.loc.name} - {title}", "layout": "chart",
                "meta": [("Location", win.loc.name), ("Checklist", title), ("Columns", "Each column is a date: weekday and day of the month"), ("Initials", ", ".join(f"{k} = {v}" for k, v in sorted(legend.items())) or "-")],
                "legend": CHART_KEY,
                "columns": [("task", "Task")] + [(f"d{i}", f"{day.strftime('%a')}\n{day.day}") for i, day in enumerate(days)],
                "rows": rows,
                "totals": [("Tasks", len(rows)), ("Completed", f"{done}/{expected}" if expected else "0/0"),
                           ("Compliance", f"{metrics.pct(done, expected)}%" if expected else "n/a")]})
        if exceptions:
            groups.append({
                "title": f"{win.loc.name} - Exceptions and follow-up", "meta": [("Location", win.loc.name)],
                "columns": [("date", "Date"), ("task", "Task"), ("status", "Status"), ("completed_by", "Completed by"),
                            ("approved_by", "Approved by"), ("reason", "Reason or comment")],
                "rows": exceptions, "totals": [("Exceptions", len(exceptions))]})
    return groups


def _attendance_groups(db: Session, now: datetime, scope, f: Filters, day_from: date, day_to: date) -> list[dict]:
    groups = []
    for win in metrics.windows(db, now, scope, f.location_id, day_from, day_to):
        stats = metrics.attendance_stats(db, win, now, f.employee_id)
        if not stats["rows"]:
            continue
        tz = win.loc.timezone
        rows = [{"date": r["day"].strftime("%d %b %Y"), "employee": r["name"], "shift": r["shift"] or "",
                 "status": r["status"].replace("_", " ").capitalize(),
                 "check_in": timeutil.to_local(r["check_in"], tz).strftime("%H:%M") if r["check_in"] else "",
                 "check_out": timeutil.to_local(r["check_out"], tz).strftime("%H:%M") if r["check_out"] else "",
                 "late": r["late_minutes"] or "", "worked": _hm(r["payable_minutes"]), "overtime": _hm(r["overtime_minutes"]),
                 "note": r["note"] or ""} for r in stats["rows"]]
        groups.append({
            "title": f"{win.loc.name} - Attendance", "meta": [("Location", win.loc.name)],
            "columns": [("date", "Date"), ("employee", "Employee"), ("shift", "Shift"), ("status", "Status"), ("check_in", "In"),
                        ("check_out", "Out"), ("late", "Late (min)"), ("worked", "Worked"), ("overtime", "Overtime"), ("note", "Note")],
            "rows": rows,
            "totals": [("Scheduled", stats["scheduled"]), ("Present", stats["present"]), ("Late", stats["late"]),
                       ("Absent", stats["absent"]), ("On leave", stats["on_leave"]), ("Week off", stats["week_off"])]})
    return groups


PRESENT_STATUSES = ("present", "late", "on_duty", "missed_checkout", "unscheduled")
LEAVE_STATUSES = ("sick_leave", "annual_leave", "unpaid_leave", "other_leave")


def _attendance_sheet_groups(db: Session, now: datetime, scope, f: Filters, day_from: date, day_to: date) -> list[dict]:
    """One page per employee: day totals first, then every scheduled, worked or recorded day."""
    people = {e.id: e for e in db.scalars(select(Employee))}
    sheets: dict[int, dict] = {}
    for win in metrics.windows(db, now, scope, f.location_id, day_from, day_to):
        tz = win.loc.timezone
        for r in metrics.attendance_stats(db, win, now, f.employee_id)["rows"]:
            sheet = sheets.setdefault(r["employee_id"], {"places": set(), "rows": []})
            sheet["places"].add(win.loc.name)
            sheet["rows"].append((r["day"], {
                "date": r["day"].strftime("%d %b %Y"), "weekday": r["day"].strftime("%a"),
                "status": r["status"].replace("_", " ").capitalize(), "_status": r["status"],
                "check_in": timeutil.to_local(r["check_in"], tz).strftime("%H:%M") if r["check_in"] else "",
                "check_out": timeutil.to_local(r["check_out"], tz).strftime("%H:%M") if r["check_out"] else "",
                "late": r["late_minutes"] or "", "worked": _hm(r["payable_minutes"]), "overtime": _hm(r["overtime_minutes"]),
                "note": r["note"] or ("No punch recorded" if r["status"] == "absent" and r["recorded"] is False else ""), "_minutes": r["payable_minutes"] or 0, "_over": r["overtime_minutes"] or 0, "_late": r["late_minutes"] or 0}))
    groups = []
    for emp_id, sheet in sorted(sheets.items(), key=lambda kv: people[kv[0]].full_name):
        emp = people[emp_id]
        rows = [row for _, row in sorted(sheet["rows"], key=lambda item: item[0]) if row["_status"] != "not_yet_due"]
        if not rows:
            continue
        count = lambda *statuses: sum(1 for r in rows if r["_status"] in statuses)  # noqa: E731
        totals = [("Days present", count(*PRESENT_STATUSES)), ("Late arrivals", sum(1 for r in rows if r["_late"] and r["_status"] in PRESENT_STATUSES)),
                  ("Week off", count("week_off")), ("Absent", count("absent")), ("On leave", count(*LEAVE_STATUSES)),
                  ("Hours worked", _hm(sum(r["_minutes"] for r in rows)) or "0:00"), ("Overtime", _hm(sum(r["_over"] for r in rows)) or "0:00")]
        for r in rows:
            for private in ("_status", "_minutes", "_over", "_late"):
                del r[private]
        groups.append({
            "title": f"{emp.full_name} ({emp.employee_code})", "layout": "sheet", "page_break": True, "summary_first": True,
            "meta": [("Employee", emp.full_name), ("Employee ID", emp.employee_code), ("Job title", emp.job_title),
                     ("Location", ", ".join(sorted(sheet["places"])))],
            "columns": [("date", "Date"), ("weekday", "Day"), ("status", "Status"), ("check_in", "In"), ("check_out", "Out"),
                        ("late", "Late (min)"), ("worked", "Worked"), ("overtime", "Overtime"), ("note", "Note")],
            "rows": rows, "totals": totals})
    return groups


def _hm(minutes: int | None) -> str:
    return "" if minutes is None else f"{minutes // 60}:{minutes % 60:02d}"


def _money(value) -> str:
    return "" if value is None else f"{value:.2f}"


def _receipt_groups(db: Session, locations: list[Location], f: Filters, day_from: date, day_to: date) -> list[dict]:
    names, suppliers = _names(db), {s.id: s.name for s in db.scalars(select(Supplier))}
    items = {i.id: i for i in db.scalars(select(InventoryItem))}
    groups = []
    for loc in locations:
        start, end = _bounds(day_from, day_to, loc.timezone)
        stmt = select(Receipt).where(Receipt.location_id == loc.id, Receipt.received_at >= start, Receipt.received_at < end)
        if f.supplier_id is not None:
            stmt = stmt.where(Receipt.supplier_id == f.supplier_id)
        docs = list(db.scalars(stmt.order_by(Receipt.received_at)))
        if not docs:
            continue
        rows = []
        lines_by_doc: dict[int, list] = {}  # every line of every document in one query, grouped by document
        for ln in db.scalars(select(ReceiptLine).where(ReceiptLine.receipt_id.in_([d.id for d in docs])).order_by(ReceiptLine.id)):
            lines_by_doc.setdefault(ln.receipt_id, []).append(ln)
        for doc in docs:
            kind = "Return" if doc.doc_type == "supplier_return" else "Receipt"
            for ln in lines_by_doc.get(doc.id, []):
                item = items[ln.item_id]
                rows.append({"date": _local(doc.received_at, loc.timezone)[:11], "type": kind, "supplier": suppliers.get(doc.supplier_id, ""),
                             "invoice": doc.invoice_number, "item": f"{item.code} - {item.name}", "qty": ln.qty,
                             "unit_cost": _money(ln.unit_cost), "discount": _money(ln.discount_amount), "line_total": _money(ln.line_total),
                             "received_by": names.get(doc.received_by, ""), "status": "Void" if doc.status == "void" else "Posted"})
        posted = [d for d in docs if d.status == "posted" and d.doc_type == "receipt" and d.total is not None]
        sub = sum((d.subtotal or 0 for d in posted), 0)
        disc = sum(((d.line_discount_total or 0) + (d.discount_amount or 0) for d in posted), 0)
        groups.append({
            "title": f"{loc.name} - Receipts and invoices", "meta": [("Location", loc.name)],
            "columns": [("date", "Date"), ("type", "Type"), ("supplier", "Supplier"), ("invoice", "Invoice"), ("item", "Item"),
                        ("qty", "Qty"), ("unit_cost", "Unit cost"), ("discount", "Discount"), ("line_total", "Line total"),
                        ("received_by", "Received by"), ("status", "Status")],
            "rows": rows,
            "totals": [("Documents", len(docs)), ("Sub total", _money(sub)), ("Total discount", _money(disc)),
                       ("Invoice total (posted receipts)", _money(sum((d.total for d in posted), 0)))]})
    return groups


def _movement_groups(db: Session, locations: list[Location], f: Filters, day_from: date, day_to: date) -> list[dict]:
    names = _names(db)
    items = {i.id: i for i in db.scalars(select(InventoryItem))}
    categories = {c.id: c.name for c in db.scalars(select(InventoryCategory))}
    groups = []
    for loc in locations:
        start, end = _bounds(day_from, day_to, loc.timezone)
        stmt = select(StockTransaction).where(StockTransaction.location_id == loc.id, StockTransaction.occurred_at >= start,
                                              StockTransaction.occurred_at < end)
        if f.movement in MOVEMENTS:
            stmt = stmt.where(StockTransaction.txn_type.in_(MOVEMENTS[f.movement]))
        if f.item_id is not None:
            stmt = stmt.where(StockTransaction.item_id == f.item_id)
        txns = list(db.scalars(stmt.order_by(StockTransaction.occurred_at, StockTransaction.id)))
        if not txns:
            continue
        rows = []
        for t in txns:
            item = items[t.item_id]
            when = _local(t.occurred_at, loc.timezone)
            rows.append({"date": when[:11], "time": when[12:], "item": f"{item.code} - {item.name}", "category": categories.get(item.category_id, ""),
                         "type": t.txn_type.replace("_", " ").capitalize(), "qty": t.qty_delta, "by": names.get(t.user_id, ""),
                         "reason": t.reason or "", "reference": f"{t.ref_type} #{t.ref_id}" if t.ref_type else ""})
        groups.append({
            "title": f"{loc.name} - Stock movements", "meta": [("Location", loc.name)],
            "columns": [("date", "Date"), ("time", "Time"), ("item", "Item"), ("category", "Category"), ("type", "Movement"),
                        ("qty", "Qty"), ("by", "By"), ("reason", "Reason"), ("reference", "Reference")],
            "rows": rows,
            "totals": [("Movements", len(txns)), ("Stock in", sum(t.qty_delta for t in txns if t.qty_delta > 0)),
                       ("Stock out", -sum(t.qty_delta for t in txns if t.qty_delta < 0)), ("Net", sum(t.qty_delta for t in txns))]})
    return groups


def build_record(db: Session, now: datetime, scope: set[int] | None, kind: str, day_from: date, day_to: date,
                 f: Filters, prepared_by: str) -> dict:
    if kind not in KINDS:
        raise ValueError("Unknown record type")
    if day_from > day_to:
        raise ValueError("The start date is after the end date")
    if (day_to - day_from).days >= MAX_DAYS:
        raise ValueError(f"A record covers at most {MAX_DAYS} days")
    locations = _locations(db, scope, f.location_id)
    if kind == "monitoring":
        groups = _monitoring_groups(db, locations, day_from, day_to, f.equipment_id)
    elif kind == "checklists":
        groups = _checklist_groups(db, locations, day_from, day_to, f.frequency, f.employee_id)
    elif kind == "checklist_chart":
        groups = _chart_groups(db, now, scope, f, day_from, day_to)
    elif kind == "attendance":
        groups = _attendance_groups(db, now, scope, f, day_from, day_to)
    elif kind == "attendance_sheet":
        groups = _attendance_sheet_groups(db, now, scope, f, day_from, day_to)
    elif kind == "receipts":
        groups = _receipt_groups(db, locations, f, day_from, day_to)
    else:
        groups = _movement_groups(db, locations, f, day_from, day_to)
    label = day_from.strftime("%d %b %Y") if day_from == day_to else f"{day_from.strftime('%d %b %Y')} to {day_to.strftime('%d %b %Y')}"
    return {"kind": kind, "title": KINDS[kind], "period": {"from": day_from.isoformat(), "to": day_to.isoformat(), "label": label},
            "locations": [loc.name for loc in locations], "prepared_by": prepared_by,
            "generated_at": now.strftime("%d %b %Y %H:%M UTC"), "groups": groups}
