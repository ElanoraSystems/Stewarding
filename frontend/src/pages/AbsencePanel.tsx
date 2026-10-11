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
import { fmtDate, label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

const ABSENCE_TYPES = ['absent', 'day_off', 'sick_leave', 'annual_leave', 'unpaid_leave', 'other_leave']

interface Absence {
  id: number
  employee_name: string
  local_date: string
  absence_type: string
  note: string | null
  status: 'active' | 'void'
  void_reason: string | null
}

const today = () => new Date().toISOString().slice(0, 10)

export function AbsencePanel() {
  const run = useRun()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [employeeId, setEmployeeId] = useState('')
  const [day, setDay] = useState(today)
  const [dayTo, setDayTo] = useState('')
  const [kind, setKind] = useState('absent')
  const [note, setNote] = useState('')
  const employees = useApi<{ items: { id: number; full_name: string }[] }>(locationId ? `/employees${qs({ location_id: locationId, status: 'active', size: 200 })}` : null)
  const list = useApi<{ items: Absence[] }>(`/absences${qs({ location_id: locationId, size: 20 })}`)

  async function record(event: FormEvent) {
    event.preventDefault()
    const ok = await run(() => api('/absences', { body: { employee_id: Number(employeeId), location_id: locationId, day, day_to: dayTo || null, absence_type: kind, note: note || null } }), 'Recorded')
    if (ok) {
      setNote('')
      list.reload()
    }
  }

  async function voidRecord(a: Absence) {
    const reason = window.prompt(`Why is the record for ${a.employee_name} on ${a.local_date} being cancelled? (at least 5 characters)`)
    if (reason && await run(() => api(`/absences/${a.id}/void`, { body: { reason } }), 'Record cancelled')) list.reload()
  }

  return (
    <Card>
      <CardHeader><CardTitle>Assign a day off, absence or leave</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={record} className="flex flex-wrap items-end gap-3">
          <Field label="Location"><LocationSelect value={locationId} onChange={(id) => { setLocationId(id); setEmployeeId('') }} /></Field>
          <Field label="Employee">
            <Select required value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              <option value="">Select</option>
              {employees.data?.items.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </Select>
          </Field>
          <Field label="From"><Input required type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
          <Field label="To (optional)" hint="For several days in a row"><Input type="date" value={dayTo} min={day} onChange={(e) => setDayTo(e.target.value)} /></Field>
          <Field label="Type">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>{ABSENCE_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}</Select>
          </Field>
          <Field label="Note"><Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></Field>
          <Button type="submit" disabled={!employeeId || !locationId}>Record</Button>
        </form>
        {list.data?.items.length === 0 ? <EmptyState title="Nothing recorded" /> : (
          <Table>
            <thead><tr><Th>Date</Th><Th>Employee</Th><Th>Type</Th><Th>Note</Th><Th /></tr></thead>
            <tbody>
              {list.data?.items.map((a) => (
                <tr key={a.id} className={a.status === 'void' ? 'opacity-60' : undefined}>
                  <Td>{fmtDate(a.local_date)}</Td>
                  <Td className="font-medium">{a.employee_name}</Td>
                  <Td><Badge tone={a.absence_type === 'absent' ? 'critical' : 'neutral'}>{label(a.absence_type)}</Badge></Td>
                  <Td>{a.status === 'void' ? `Cancelled: ${a.void_reason}` : a.note ?? '-'}</Td>
                  <Td>{a.status === 'active' && <Button size="sm" variant="outline" onClick={() => voidRecord(a)}>Cancel</Button>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
