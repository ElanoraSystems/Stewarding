import { useState, type FormEvent } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { EmployeeRow } from '@/pages/EmployeeForm'

interface Today {
  employee_id: number
  name: string
  shift: string
  shift_start: string
  checked_in: boolean
  late_minutes: number
  on_duty: boolean
  day_type: 'work' | 'week_off' | 'absence'
  absence_type: string | null
}
interface Shift {
  id: number
  name: string
  start_time: string
  end_time: string
  grace_minutes: number
  kind: 'work' | 'weekoff'
  active: boolean
}
interface Assignment {
  id: number
  employee_id: number
  shift_id: number
  weekday: number
  valid_from: string
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function RosterPage() {
  const { me } = useAuth()
  const run = useRun()
  const canManage = me?.permissions.includes('roster.manage') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const [employeeId, setEmployeeId] = useState('')
  const [shiftId, setShiftId] = useState('')
  const [weekdays, setWeekdays] = useState<number[]>([0, 1, 2, 3, 4])
  const [validFrom, setValidFrom] = useState('')

  const today = useApi<Today[]>(locationId ? `/roster/today${qs({ location_id: locationId })}` : null)
  const shifts = useApi<Shift[]>('/roster/shifts')
  const assignments = useApi<Assignment[]>(locationId ? `/roster/assignments${qs({ location_id: locationId })}` : null)
  const people = useApi<{ items: EmployeeRow[] }>(locationId ? `/employees${qs({ location_id: locationId, status: 'active', size: 200 })}` : null)
  const names = new Map(people.data?.items.map((e) => [e.id, e.full_name]))
  const shiftNames = new Map(shifts.data?.map((s) => [s.id, s.name]))

  async function assign(event: FormEvent) {
    event.preventDefault()
    const ok = await run(
      () => api('/roster/assignments', { body: { employee_id: Number(employeeId), shift_id: Number(shiftId), location_id: locationId, weekdays, valid_from: validFrom } }),
      'Shift assigned',
    )
    if (ok) assignments.reload()
  }

  async function end(id: number) {
    if (await run(() => api(`/roster/assignments/${id}`, { method: 'DELETE' }), 'Assignment ended')) assignments.reload()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Shift &amp; Duty Roster</h1>
        <LocationSelect value={locationId} onChange={setLocationId} />
      </div>

      <Card>
        <CardHeader><CardTitle>Scheduled today</CardTitle></CardHeader>
        <CardContent>
          {today.data?.length === 0 ? <EmptyState title="Nobody is scheduled today" /> : (
            <ul className="divide-y divide-border">
              {today.data?.map((p) => (
                <li key={p.employee_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-ink-muted">{p.day_type === 'week_off' ? p.shift : `${p.shift} from ${p.shift_start.slice(0, 5)}`}</span>
                  <span className="space-x-1">
                    {p.day_type === 'work' ? (
                      <Badge tone={p.on_duty ? 'ok' : p.checked_in ? 'neutral' : 'warn'}>
                        {p.on_duty ? 'On duty' : p.checked_in ? 'Checked out' : 'Not checked in'}
                      </Badge>
                    ) : p.day_type === 'week_off' ? <Badge>Week off</Badge> : <Badge tone={p.absence_type === 'absent' ? 'critical' : 'neutral'}>{label(p.absence_type ?? 'absent')}</Badge>}
                    {p.late_minutes > 0 && <Badge tone="warn">Late {p.late_minutes}m</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Weekly assignments</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Table>
            <thead><tr><Th>Employee</Th><Th>Day</Th><Th>Shift</Th><Th>From</Th>{canManage && <Th />}</tr></thead>
            <tbody>
              {assignments.data?.map((a) => (
                <tr key={a.id}>
                  <Td>{names.get(a.employee_id) ?? a.employee_id}</Td>
                  <Td>{DAYS[a.weekday]}</Td>
                  <Td>{shiftNames.get(a.shift_id)}</Td>
                  <Td>{a.valid_from}</Td>
                  {canManage && <Td><Button size="sm" variant="outline" onClick={() => end(a.id)}>End</Button></Td>}
                </tr>
              ))}
            </tbody>
          </Table>
          {assignments.data?.length === 0 && <EmptyState title="No assignments at this location" />}

          {canManage && (
            <form onSubmit={assign} className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
              <Field label="Employee" hint={people.data?.items.length === 0 ? 'Nobody is assigned to this location yet.' : undefined}>
                <Select required value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
                  <option value="">{people.data?.items.length === 0 ? 'No employees at this location' : 'Select'}</option>
                  {people.data?.items.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                </Select>
              </Field>
              <Field label="Shift">
                <Select required value={shiftId} onChange={(e) => setShiftId(e.target.value)}>
                  <option value="">Select</option>
                  {shifts.data?.filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.kind === 'weekoff' ? `${s.name} (week off)` : `${s.name} (${s.start_time.slice(0, 5)}-${s.end_time.slice(0, 5)})`}</option>)}
                </Select>
              </Field>
              <Field label="Valid from"><Input required type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} /></Field>
              <fieldset className="flex gap-2 text-sm">
                <legend className="mb-1 font-medium">Days</legend>
                {DAYS.map((d, i) => (
                  <label key={d} className="flex items-center gap-1">
                    <input type="checkbox" checked={weekdays.includes(i)}
                      onChange={() => setWeekdays((w) => (w.includes(i) ? w.filter((x) => x !== i) : [...w, i]))} />
                    {d}
                  </label>
                ))}
              </fieldset>
              <Button type="submit" disabled={weekdays.length === 0} title={weekdays.length === 0 ? 'Choose at least one day' : undefined}>Assign</Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
