export interface Note {
  id: number
  kind: string
  priority: string
  title: string
  body: string | null
  location_id: number | null
  link: string | null
  created_at: string
  read_at: string | null
  requires_ack: boolean
  acknowledged_at: string | null
  action_needed: boolean
}

/** Alerts that ask for a real decision; every other alert is a warning to be acknowledged, so it has one button, not Approve and Reject. */
export const DECISION_KINDS = ['breakage_approval']
export const needsDecision = (n: Note) => n.requires_ack && !n.acknowledged_at && DECISION_KINDS.includes(n.kind)
export const needsAcknowledging = (n: Note) => n.requires_ack && !n.acknowledged_at && !DECISION_KINDS.includes(n.kind)

export const KIND_TITLE: Record<string, string> = {
  task_escalated: 'Escalation to manager', monitoring_failed: 'Reading out of range', monitoring_escalated: 'Monitoring escalated',
  retest_due: 'Retest due', task_overdue: 'Task overdue', time_out_missing: 'Check-out missing',
  missed_checkout: 'Not checked out', no_checkin: 'Not checked in', monitoring_overdue: 'Monitoring check overdue',
}
const day = (n: Note) => new Date(n.created_at).toLocaleDateString('en-CA')

/** Neighbouring alerts of one kind, place and day (the list is newest first) become one group, so repeats stop filling the page.
 *  Only kinds with a general heading are grouped: any other alert names its own person or item, so it stays a card of its own. */
export function groupNotes(items: Note[]): Note[][] {
  const out: Note[][] = []
  for (const n of items) {
    const group = out.at(-1)
    const first = group?.[0]
    if (group && first && KIND_TITLE[n.kind] && first.kind === n.kind && first.location_id === n.location_id && day(first) === day(n) && first.action_needed === n.action_needed) group.push(n)
    else out.push([n])
  }
  return out
}

