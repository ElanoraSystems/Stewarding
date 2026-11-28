export type ExtraFilter = 'employee' | 'frequency' | 'monitoringPoint' | 'supplier' | 'movement' | 'item' | 'status' | 'foodGroup' | 'monitoringType' | 'checklist' | 'costView' | 'readingLayout' | 'lotCode'

export interface ReportDef {
  key: string
  title: string
  about?: string  // one or two plain sentences under the heading: what this report shows and when to use it
  section: string
  filters: ExtraFilter[]
  statuses?: [string, string][]
  summary?: boolean
  pack?: boolean
}

export const REPORTS: ReportDef[] = [
  { key: 'attendance', title: 'Attendance', section: 'People', filters: ['employee', 'status'],
    statuses: [['present', 'Present'], ['late', 'Late'], ['absent', 'Absent'], ['leave', 'On leave'], ['week_off', 'Week off']] },
  { key: 'attendance_sheet', title: 'Employee attendance sheet', section: 'People', filters: ['employee'] },
  { key: 'checklist_chart', title: 'Checklist sign-off sheet', section: 'Checklists', filters: ['checklist', 'frequency'],
    about: 'A grid with the tasks down the side and the dates across. Each box is a tick or a cross with the initials of who did it and who approved it, with the compliance percentage and the exceptions. It is the sheet to print for a week or a month.' },
  { key: 'approvals', title: 'Approval decisions', section: 'Overview', filters: ['status'],
    about: 'Every approval and rejection with who decided, when and their comment, across checklist tasks, monitoring readings and alerts. It shows the decisions only, not the work itself.',
    statuses: [['approved', 'Approved'], ['rejected', 'Rejected']] },
  { key: 'checklists', title: 'Checklist record', section: 'Checklists', filters: ['checklist', 'frequency', 'employee', 'status'],
    about: 'One row for every task: its date and status, who did it and when, how late and why, any reading or comment, and who approved it. Use it to follow what happened to a particular task.',
    statuses: [['pending', 'Not done'], ['completed', 'Done'], ['pending_verification', 'Awaiting approval'], ['verified', 'Approved'], ['failed', 'Rejected'], ['waived', 'Waived']] },
  { key: 'inspector_pack', title: 'Inspector pack', section: 'Food safety', filters: [], pack: true },
  { key: 'monitoring', title: 'Monitoring record', section: 'Food safety', filters: ['monitoringType', 'monitoringPoint', 'status', 'readingLayout'],
    statuses: [['failed', 'Failed'], ['passed', 'Passed'], ['awaiting', 'Awaiting approval']] },
  { key: 'calibration', title: 'Probe calibration record', section: 'Food safety', filters: ['status'],
    statuses: [['passed', 'Passed'], ['failed', 'Failed']] },
  { key: 'lots', title: 'Lot register', section: 'Food safety', filters: ['supplier', 'foodGroup', 'status'],
    statuses: [['active', 'Active'], ['on_hold', 'On hold'], ['used_up', 'Used up'], ['discarded', 'Discarded']] },
  { key: 'recall', title: 'Lot recall trace', section: 'Food safety', filters: ['lotCode', 'supplier'] },
  // receipts and stock movements are downloaded from the Receiving and Transactions lists, with the filters shown there
  { key: 'stock_cost', title: 'Stock cost report', section: 'Stock', filters: ['costView'] },
  { key: 'inventory_detail', title: 'Detailed inventory report (by location and item)', section: 'Stock', filters: [] },
  { key: 'summary', title: 'Operations summary', section: 'Overview', filters: [], summary: true },
]

export const FOOD_GROUPS = [
  ['poultry', 'Poultry'], ['red_meat', 'Red meat'], ['seafood', 'Seafood'], ['dairy', 'Dairy'], ['eggs', 'Eggs'], ['other', 'Other'],
]

export const SECTIONS = ['People', 'Checklists', 'Food safety', 'Stock', 'Overview']

export const MOVEMENTS = [
  ['receipts', 'Receipts'], ['issues', 'Issues'], ['returns', 'Returns'], ['transfers', 'Transfers'],
  ['breakage', 'Breakage and damage'], ['adjustments', 'Adjustments'], ['opening', 'Opening stock'],
]
