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
import { label, weekdaysText } from '@/lib/format'
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
  valid_to: string | null
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const PAGE = 25

interface Group {
  key: string
  employee_id: number
  shift_id: number
  valid_from: string
  valid_to: string | null
  weekdays: number[]
  ids: number[]
}

export function RosterPage() {
  const { me } = useAuth()
  const run = useRun()
  const canManage = me?.permissions.includes('roster.manage') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const [employeeId, setEmployeeId] = useState('')
  const [shiftId, setShiftId] = useState('')
  const [weekdays, setWeekdays] = useState<number[]>([0, 1, 2, 3, 4])
  const [validFrom, setValidFrom] = useState('')
  const [validTo, setValidTo] = useState('')
  const [search, setSearch] = useState('')
  const [shiftFilter, setShiftFilter] = useState('')
  const [shown, setShown] = useState(PAGE)

  const today = useApi<Today[]>(locationId ? `/roster/today${qs({ location_id: locationId })}` : null)
  const shifts = useApi<Shift[]>('/roster/shifts')
  const assignments = useApi<Assignment[]>(locationId ? `/roster/assignments${qs({ location_id: locationId })}` : null)
  const people = useApi<{ items: EmployeeRow[] }>(locationId ? `/employees${qs({ location_id: locationId, status: 'active', size: 200 })}` : null)
  const names = new Map(people.data?.items.map((e) => [e.id, e.full_name]))
  const shiftNames = new Map(shifts.data?.map((s) => [s.id, s.name]))

  async function assign(event: FormEvent) {
    event.preventDefault()
    const ok = await run(
      () => api('/roster/assignments', { body: { employee_id: Number(employeeId), shift_id: Number(shiftId), location_id: locationId, weekdays, valid_from: validFrom, valid_to: validTo || null } }),
      'Shift assigned',
    )
    if (ok) assignments.reload()
  }

  async function end(group: Group) {
    if (await run(() => api('/roster/assignments/end', { body: { ids: group.ids } }), 'Assignment ended')) assignments.reload()
  }

  // one row per employee, shift and period, however many weekdays it covers
  const groups = (() => {
    const out = new Map<string, Group>()
    for (const a of assignments.data ?? []) {
      const key = `${a.employee_id}|${a.shift_id}|${a.valid_from}|${a.valid_to ?? ''}`
      const group = out.get(key)
      if (group) {
        group.weekdays.push(a.weekday)
        group.ids.push(a.id)
      } else out.set(key, { key, employee_id: a.employee_id, shift_id: a.shift_id, valid_from: a.valid_from, valid_to: a.valid_to, weekdays: [a.weekday], ids: [a.id] })
    }
    const needle = search.trim().toLowerCase()
    return [...out.values()]
      .map((g) => ({ ...g, weekdays: [...g.weekdays].sort((x, y) => x - y) }))
      .filter((g) => (!shiftFilter || String(g.shift_id) === shiftFilter) && (!needle || (names.get(g.employee_id) ?? '').toLowerCase().includes(needle)))
      .sort((x, y) => (names.get(x.employee_id) ?? '').localeCompare(names.get(y.employee_id) ?? '') || x.valid_from.localeCompare(y.valid_from))
  })()

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
                <li key={`${p.employee_id}-${p.shift}`} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
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
          <div className="flex flex-wrap gap-3">
            <Input aria-label="Search employees" className="max-w-56" placeholder="Search employee" value={search}
              onChange={(e) => { setSearch(e.target.value); setShown(PAGE) }} />
            <Select aria-label="Shift" className="w-auto" value={shiftFilter} onChange={(e) => { setShiftFilter(e.target.value); setShown(PAGE) }}>
              <option value="">All shifts</option>
              {shifts.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </div>
          <Table>
            <thead><tr><Th>Employee</Th><Th>Shift</Th><Th>Days</Th><Th>From</Th><Th>Until</Th>{canManage && <Th />}</tr></thead>
            <tbody>
              {groups.slice(0, shown).map((g) => (
                <tr key={g.key}>
                  <Td>{names.get(g.employee_id) ?? g.employee_id}</Td>
                  <Td>{shiftNames.get(g.shift_id)}</Td>
                  <Td>{weekdaysText(g.weekdays)}</Td>
                  <Td>{g.valid_from}</Td>
                  <Td>{g.valid_to ?? 'Ongoing'}</Td>
                  {canManage && <Td><Button size="sm" variant="outline" onClick={() => end(g)}>End</Button></Td>}
                </tr>
              ))}
            </tbody>
          </Table>
          {groups.length > shown && <Button variant="outline" onClick={() => setShown((n) => n + PAGE)}>Show more ({groups.length - shown} left)</Button>}
          {assignments.data && groups.length === 0 && <EmptyState title={assignments.data.length === 0 ? 'No assignments at this location' : 'No assignment matches'} />}

          {canManage && (
            <form onSubmit={assign} className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
              <Field label="Employee">
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
              <Field label="Valid until (optional)"><Input type="date" min={validFrom || undefined} value={validTo} onChange={(e) => setValidTo(e.target.value)} /></Field>
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
