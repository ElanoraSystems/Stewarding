import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

const GROUPS: { title: string; hint: string; keys: Record<string, string> }[] = [
  {
    title: 'Reminders and escalation',
    hint: 'When people are reminded about a deadline and when an overdue task moves up to a supervisor, then a manager.',
    keys: {
      'reminder.lead_minutes': 'Reminder before a deadline (minutes)',
      'escalation.supervisor_after_minutes': 'Escalate to supervisor after (minutes overdue)',
      'escalation.manager_after_minutes': 'Escalate to manager after (minutes overdue)',
    },
  },
  {
    title: 'Monitoring',
    hint: 'Timing around checks, retests and repeat failures. The limits and frequency of each check are set per monitoring point under Monitoring setup.',
    keys: {
      'temp.due_grace_minutes': 'Grace period for a due check (minutes)',
      'temp.retest_minutes': 'Retest due after corrective action (minutes)',
      'temp.escalate_after_minutes': 'Escalate an unresolved failed check after (minutes)',
      'temp.repeat_failure_count': 'Repeat-failure alert at this many failures',
      'temp.repeat_failure_days': 'Repeat-failure window (days)',
    },
  },
  {
    title: 'Approvals',
    hint: 'A supervisor or a manager can approve; whoever gets there first approves, and nobody approves their own work.',
    keys: { 'approval.checklists': 'Every completed checklist task needs approval (1 = yes, 0 = only tasks marked for verification)' },
  },
  {
    title: 'Breakage approval',
    hint: 'An incident at or above either value needs a manager before stock is deducted.',
    keys: {
      'breakage.approval_qty': 'Approval needed from this quantity',
      'breakage.approval_cost': 'Approval needed from this estimated cost',
    },
  },
  {
    title: 'Attendance',
    hint: 'How long an open check-in stays before it is flagged as a missed check-out, and how vague a phone position may be at a location with a geofence (0 turns the limit off).',
    keys: { 'attendance.missed_checkout_hours': 'Missed check-out after (hours)', 'attendance.max_accuracy_m': 'Largest location error accepted (metres)' },
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
            <p className="text-sm text-ink-muted">{group.hint}</p>
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
