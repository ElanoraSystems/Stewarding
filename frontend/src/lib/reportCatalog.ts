export type ExtraFilter = 'employee' | 'frequency' | 'monitoringPoint' | 'supplier' | 'movement' | 'item'

export interface ReportDef {
  key: string
  title: string
  blurb: string
  section: string
  filters: ExtraFilter[]
  summary?: boolean
}

export const REPORTS: ReportDef[] = [
  { key: 'attendance', title: 'Attendance', section: 'People', filters: ['employee'],
    blurb: 'Who worked, when they checked in and out, late arrivals, absences, leave and week offs, by location.' },
  { key: 'attendance_sheet', title: 'Employee attendance sheet', section: 'People', filters: ['employee'],
    blurb: 'One page per employee: days present, week off, absent, leave and hours worked, with every day listed. Ready to sign.' },
  { key: 'checklist_chart', title: 'Checklist completion chart', section: 'Checklists', filters: ['frequency'],
    blurb: 'Tasks down the page, dates across, a tick for each task done. Shows who completed and who approved, with exceptions.' },
  { key: 'checklists', title: 'Checklist record', section: 'Checklists', filters: ['frequency', 'employee'],
    blurb: 'Every task with the time it was completed, who did it and who approved it. Suits longer periods.' },
  { key: 'monitoring', title: 'Monitoring record', section: 'Food safety', filters: ['monitoringPoint'],
    blurb: 'Each reading with value, limits, result, who recorded it, who approved it and any corrective action.' },
  { key: 'receipts', title: 'Receipts and invoices', section: 'Stock', filters: ['supplier'],
    blurb: 'Deliveries and returns by invoice with unit cost, discounts and totals.' },
  { key: 'movements', title: 'Stock issues and movements', section: 'Stock', filters: ['movement', 'item'],
    blurb: 'Every stock movement: receipts, issues, returns, transfers, breakage and adjustments, with who and why.' },
  { key: 'stock_cost', title: 'Stock cost report', section: 'Stock', filters: [],
    blurb: 'Opening value, purchases, closing value and the cost consumed for each item, at weighted average cost, with issues, breakage and count losses shown separately.' },
  { key: 'summary', title: 'Operations summary', section: 'Overview', filters: [], summary: true,
    blurb: 'Daily, weekly or monthly scorecard across attendance, checklists, monitoring, breakage and stock.' },
]

export const SECTIONS = ['People', 'Checklists', 'Food safety', 'Stock', 'Overview']

export const MOVEMENTS = [
  ['receipts', 'Receipts'], ['issues', 'Issues'], ['returns', 'Returns'], ['transfers', 'Transfers'],
  ['breakage', 'Breakage and damage'], ['adjustments', 'Adjustments'], ['opening', 'Opening stock'],
]
