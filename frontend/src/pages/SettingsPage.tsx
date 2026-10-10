import { useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { Skeleton, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface LocationRow {
  id: number
  code: string
  name: string
  kind: string
  timezone: string
  active: boolean
  pin_required: boolean
}

interface SettingsData {
  settings: Record<string, number>
  locations: LocationRow[]
}

interface Shift {
  id: number
  name: string
  start_time: string
  end_time: string
  grace_minutes: number
  break_minutes: number
  overtime_after_minutes: number | null
}

const LABELS: Record<string, string> = {
  'reminder.lead_minutes': 'Reminder before a deadline (minutes)',
  'escalation.supervisor_after_minutes': 'Escalate overdue tasks to supervisor after (minutes)',
  'escalation.manager_after_minutes': 'Escalate overdue tasks to manager after (minutes)',
  'temp.due_grace_minutes': 'Temperature check grace period (minutes)',
  'temp.retest_minutes': 'Retest due after corrective action (minutes)',
  'temp.escalate_after_minutes': 'Escalate unresolved failed reading to manager after (minutes)',
  'temp.repeat_failure_count': 'Repeat-failure alert at this many failures',
  'temp.repeat_failure_days': 'Repeat-failure window (days)',
  'breakage.approval_qty': 'Breakage needs manager approval from this quantity',
  'breakage.approval_cost': 'Breakage needs manager approval from this cost',
  'attendance.missed_checkout_hours': 'Missed check-out after (hours)',
}

const KINDS = ['kitchen', 'restaurant', 'bar', 'banquet', 'station', 'other']
const BLANK = { id: null as number | null, code: '', name: '', kind: 'kitchen', timezone: 'UTC', active: true, pin: '', clear_pin: false }

export function SettingsPage() {
  const run = useRun()
  const { data, reload } = useApi<SettingsData>('/settings')
  const shifts = useApi<Shift[]>('/roster/shifts')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [loc, setLoc] = useState<typeof BLANK | null>(null)
  const [shift, setShift] = useState({ name: '', start: '06:00', end: '14:00', grace: '10', brk: '0' })

  async function saveSettings(event: FormEvent) {
    event.preventDefault()
    const values = Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)]))
    if (Object.keys(values).length && (await run(() => api('/settings', { method: 'PUT', body: { values } }), 'Settings saved'))) {
      setDraft({})
      reload()
    }
  }

  async function saveLocation(event: FormEvent) {
    event.preventDefault()
    if (!loc) return
    const body = loc.id
      ? { name: loc.name, kind: loc.kind, timezone: loc.timezone, active: loc.active, pin: loc.pin || undefined, clear_pin: loc.clear_pin }
      : { code: loc.code, name: loc.name, kind: loc.kind, timezone: loc.timezone, pin: loc.pin || undefined }
    const ok = await run(() => api(loc.id ? `/settings/locations/${loc.id}` : '/settings/locations', { method: loc.id ? 'PUT' : 'POST', body }), 'Location saved')
    if (ok) {
      setLoc(null)
      reload()
    }
  }

  async function addShift(event: FormEvent) {
    event.preventDefault()
    const ok = await run(() => api('/roster/shifts', { body: {
      name: shift.name, start_time: `${shift.start}:00`, end_time: `${shift.end}:00`, grace_minutes: Number(shift.grace), break_minutes: Number(shift.brk) } }), 'Shift added')
    if (ok) {
      setShift({ ...shift, name: '' })
      shifts.reload()
    }
  }

  if (!data) return <Skeleton className="h-64 w-full" />
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Card>
        <CardHeader><CardTitle>Notification, escalation and approval rules</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={saveSettings} className="grid gap-3 sm:grid-cols-2">
            {Object.entries(data.settings).map(([key, value]) => (
              <Field key={key} label={LABELS[key] ?? key}>
                <Input type="number" min={0} value={draft[key] ?? String(value)} onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />
              </Field>
            ))}
            <div className="sm:col-span-2"><Button type="submit" disabled={Object.keys(draft).length === 0}>Save settings</Button></div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="flex items-center justify-between">Locations <Button size="sm" onClick={() => setLoc({ ...BLANK })}>Add location</Button></CardTitle></CardHeader>
        <CardContent>
          <Table>
            <thead><tr><Th>Code</Th><Th>Name</Th><Th>Type</Th><Th>Time zone</Th><Th>Status</Th><Th /></tr></thead>
            <tbody>
              {data.locations.map((l) => (
                <tr key={l.id}>
                  <Td>{l.code}</Td><Td className="font-medium">{l.name}</Td><Td>{l.kind}</Td><Td>{l.timezone}</Td>
                  <Td><Badge tone={l.active ? 'ok' : 'neutral'}>{l.active ? 'Active' : 'Inactive'}</Badge>{l.pin_required && <Badge className="ml-1">PIN</Badge>}</Td>
                  <Td><Button size="sm" variant="outline" onClick={() => setLoc({ ...BLANK, ...l, pin: '' })}>Edit</Button></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Shifts and working hours</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Table>
            <thead><tr><Th>Shift</Th><Th>Hours</Th><Th>Late grace</Th><Th>Break</Th></tr></thead>
            <tbody>
              {shifts.data?.map((s) => (
                <tr key={s.id}><Td className="font-medium">{s.name}</Td><Td>{s.start_time.slice(0, 5)} - {s.end_time.slice(0, 5)}</Td><Td>{s.grace_minutes} min</Td><Td>{s.break_minutes} min</Td></tr>
              ))}
            </tbody>
          </Table>
          <form onSubmit={addShift} className="flex flex-wrap items-end gap-3">
            <Field label="Name"><Input required value={shift.name} onChange={(e) => setShift({ ...shift, name: e.target.value })} /></Field>
            <Field label="Start"><Input type="time" value={shift.start} onChange={(e) => setShift({ ...shift, start: e.target.value })} /></Field>
            <Field label="End"><Input type="time" value={shift.end} onChange={(e) => setShift({ ...shift, end: e.target.value })} /></Field>
            <Field label="Late grace (min)"><Input type="number" min={0} className="w-28" value={shift.grace} onChange={(e) => setShift({ ...shift, grace: e.target.value })} /></Field>
            <Field label="Break (min)"><Input type="number" min={0} className="w-28" value={shift.brk} onChange={(e) => setShift({ ...shift, brk: e.target.value })} /></Field>
            <Button type="submit">Add shift</Button>
          </form>
        </CardContent>
      </Card>

      <Modal open={loc !== null} title={loc?.id ? 'Edit location' : 'Add location'} onClose={() => setLoc(null)}>
        {loc && (
          <form onSubmit={saveLocation} className="space-y-3">
            {!loc.id && <Field label="Code"><Input required value={loc.code} onChange={(e) => setLoc({ ...loc, code: e.target.value })} /></Field>}
            <Field label="Name"><Input required value={loc.name} onChange={(e) => setLoc({ ...loc, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type"><Select value={loc.kind} onChange={(e) => setLoc({ ...loc, kind: e.target.value })}>{KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</Select></Field>
              <Field label="Time zone (IANA)"><Input required value={loc.timezone} onChange={(e) => setLoc({ ...loc, timezone: e.target.value })} /></Field>
            </div>
            <Field label="Check-in PIN (4-8 digits)" hint="Leave blank to keep the current PIN."><Input inputMode="numeric" autoComplete="off" value={loc.pin} onChange={(e) => setLoc({ ...loc, pin: e.target.value })} /></Field>
            {loc.id && (
              <>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={loc.clear_pin} onChange={(e) => setLoc({ ...loc, clear_pin: e.target.checked })} /> Remove the PIN requirement</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={loc.active} onChange={(e) => setLoc({ ...loc, active: e.target.checked })} /> Location is active</label>
              </>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setLoc(null)}>Cancel</Button>
              <Button type="submit">Save</Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
