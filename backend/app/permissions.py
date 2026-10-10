MANAGER = "manager"
SUPERVISOR = "supervisor"
STEWARD = "steward"

ALL_PERMISSIONS = [
    "dashboard.view",
    "employee.view", "employee.manage",
    "attendance.self", "attendance.view", "attendance.correct",
    "roster.view", "roster.manage",
    "checklist.view", "checklist.complete", "checklist.verify", "checklist.configure",
    "task.assign",
    "temp.view", "temp.record", "temp.review",
    "equipment.view", "equipment.manage",
    "inventory.view", "inventory.count", "inventory.manage",
    "stock.transfer", "stock.approve",
    "breakage.view", "breakage.report", "breakage.review", "breakage.approve",
    "notification.view",
    "report.view", "report.export",
    "settings.manage",
    "audit.view",
]

SUPERVISOR_PERMISSIONS = [
    "dashboard.view", "employee.view", "attendance.self", "attendance.view", "roster.view",
    "checklist.view", "checklist.complete", "checklist.verify", "task.assign",
    "temp.view", "temp.record", "temp.review", "equipment.view",
    "inventory.view", "inventory.count", "stock.transfer",
    "breakage.view", "breakage.report", "breakage.review",
    "notification.view", "report.view",
]

STEWARD_PERMISSIONS = [
    "dashboard.view", "attendance.self", "checklist.view", "checklist.complete",
    "temp.view", "temp.record", "inventory.view", "breakage.report", "notification.view",
]

ROLE_PERMISSIONS = {
    MANAGER: ALL_PERMISSIONS,
    SUPERVISOR: SUPERVISOR_PERMISSIONS,
    STEWARD: STEWARD_PERMISSIONS,
}

# key, label, permission that grants sight of the module
MODULES = [
    ("dashboard", "Dashboard", "dashboard.view"),
    ("employees", "Employees", "employee.view"),
    ("attendance", "Attendance", "attendance.self"),
    ("roster", "Shift & Duty Roster", "roster.view"),
    ("daily-checklists", "Daily Checklists", "checklist.view"),
    ("weekly-checklists", "Weekly Checklists", "checklist.view"),
    ("temperature", "Temperature Monitoring", "temp.view"),
    ("equipment", "Equipment Management", "equipment.view"),
    ("crockery", "Crockery Inventory", "inventory.view"),
    ("smallware", "Kitchen Smallware Inventory", "inventory.view"),
    ("stock-movements", "Stock Movements & Transfers", "stock.transfer"),
    ("breakage", "Breakage & Damage Logs", "breakage.report"),
    ("tasks", "Tasks & Notifications", "notification.view"),
    ("reports", "Reports & Analytics", "report.view"),
    ("settings", "Settings", "settings.manage"),
    ("audit", "Audit Logs", "audit.view"),
]
