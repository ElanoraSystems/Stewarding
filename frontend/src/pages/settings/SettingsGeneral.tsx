import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

const GROUPS: { title: string; keys: Record<string, string> }[] = [
  {
    title: 'Reminders and escalation',
    keys: {
      'reminder.lead_minutes': 'Reminder before a deadline (minutes)',
      'escalation.supervisor_after_minutes': 'Escalate to supervisor after (minutes overdue)',
      'escalation.manager_after_minutes': 'Escalate to manager after (minutes overdue)',
    },
  },
  {
    title: 'Monitoring',
    keys: {
      'temp.due_grace_minutes': 'Grace period for a due check (minutes)',
      'temp.retest_minutes': 'Retest due after corrective action (minutes)',
      'temp.escalate_after_minutes': 'Escalate an unresolved failed check after (minutes)',
      'temp.pending_alert_hours': 'Warn when a time out is still missing after (hours, 0 = never)',
      'temp.repeat_failure_count': 'Repeat-failure alert at this many failures',
      'temp.repeat_failure_days': 'Repeat-failure window (days)',
    },
  },
  {
    title: 'Approvals',
    keys: { 'approval.checklists': 'Every completed checklist task needs approval (1 = yes, 0 = only tasks marked for verification)' },
  },
  {
    title: 'Breakage approval',
    keys: {
      'breakage.approval_qty': 'Approval needed from this quantity',
      'breakage.approval_cost': 'Approval needed from this estimated cost',
    },
  },
  {
    title: 'Attendance',
    keys: {
      'attendance.missed_checkout_hours': 'Missed check-out after (hours)',
      'attendance.max_accuracy_m': 'Largest location error accepted (metres)',
      'attendance.face_required': 'Require face verification to check in and out (1 = on, 0 = off)',
      'attendance.face_liveness': 'Ask for a live head-turn check and keep a snapshot with each face check-in and check-out (1 = on, 0 = off)',
      'attendance.snapshot_days': 'Keep face-check snapshots for (days, 0 = keep them)',
      'attendance.face_match_max': 'Face match strictness (10 to 80, lower is stricter)',
    },
  },
]

export function SettingsGeneral() {
  const run = useRun()
  const { data, reload } = useApi<{ settings: Record<string, number> }>('/settings')
  const [draft, setDraft] = useState<Record<string, string>>({})

  async function save(event: FormEvent) {
    event.preventDefault()
    const values = Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)]))
    if (await run(() => api('/settings', { method: 'PUT', body: { values } }), 'Settings saved')) {
      setDraft({})
      reload()
    }
  }

  if (!data) return <Skeleton className="h-64 w-full" />
  return (
    <form onSubmit={save} className="space-y-4">
      {GROUPS.map((group) => (
        <Card key={group.title}>
          <CardHeader>
            <CardTitle>{group.title}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {Object.entries(group.keys).map(([key, text]) => (
              <Field key={key} label={text}>
                <Input type="number" min={0} value={draft[key] ?? String(data.settings[key])}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />
              </Field>
            ))}
          </CardContent>
        </Card>
      ))}
      <Button type="submit" disabled={Object.keys(draft).length === 0}>Save settings</Button>
    </form>
  )
}
