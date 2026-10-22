export type ExtraFilter = 'employee' | 'frequency' | 'monitoringPoint' | 'supplier' | 'movement' | 'item'

export interface ReportDef {
  key: string
  title: string
  section: string
  filters: ExtraFilter[]
  summary?: boolean
}

export const REPORTS: ReportDef[] = [
  { key: 'attendance', title: 'Attendance', section: 'People', filters: ['employee'] },
  { key: 'attendance_sheet', title: 'Employee attendance sheet', section: 'People', filters: ['employee'] },
  { key: 'checklist_chart', title: 'Checklist completion chart', section: 'Checklists', filters: ['frequency'] },
  { key: 'checklists', title: 'Checklist record', section: 'Checklists', filters: ['frequency', 'employee'] },
  { key: 'monitoring', title: 'Monitoring record', section: 'Food safety', filters: ['monitoringPoint'] },
  { key: 'receipts', title: 'Receipts and invoices', section: 'Stock', filters: ['supplier'] },
  { key: 'movements', title: 'Stock issues and movements', section: 'Stock', filters: ['movement', 'item'] },
  { key: 'stock_cost', title: 'Stock cost report', section: 'Stock', filters: [] },
  { key: 'stock_cost_category', title: 'Stock cost by category', section: 'Stock', filters: [] },
  { key: 'summary', title: 'Operations summary', section: 'Overview', filters: [], summary: true },
]

export const SECTIONS = ['People', 'Checklists', 'Food safety', 'Stock', 'Overview']

export const MOVEMENTS = [
  ['receipts', 'Receipts'], ['issues', 'Issues'], ['returns', 'Returns'], ['transfers', 'Transfers'],
  ['breakage', 'Breakage and damage'], ['adjustments', 'Adjustments'], ['opening', 'Opening stock'],
]
