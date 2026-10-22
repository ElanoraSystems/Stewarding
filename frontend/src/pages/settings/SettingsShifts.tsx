import { useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Shift {
  id: number
  kind: 'work' | 'weekoff'
  name: string
  start_time: string
  end_time: string
  grace_minutes: number
  break_minutes: number
  overtime_after_minutes: number | null
  active: boolean
}

const hhmm = (t: string) => t.slice(0, 5)

export function SettingsShifts() {
  const run = useRun()
  const { data, reload } = useApi<Shift[]>('/roster/shifts')
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState({ kind: 'work', name: '', start: '06:00', end: '14:00', grace: '10', brk: '0', overtime: '' })

  function edit(shift: Shift | null) {
    setEditing(shift?.id ?? null)
    setForm(shift
      ? { kind: shift.kind, name: shift.name, start: hhmm(shift.start_time), end: hhmm(shift.end_time), grace: String(shift.grace_minutes),
          brk: String(shift.break_minutes), overtime: shift.overtime_after_minutes == null ? '' : String(shift.overtime_after_minutes) }
      : { kind: 'work', name: '', start: '06:00', end: '14:00', grace: '10', brk: '0', overtime: '' })
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    const body = {
      kind: form.kind, name: form.name, start_time: `${form.start}:00`, end_time: `${form.end}:00`, grace_minutes: Number(form.grace),
      break_minutes: Number(form.brk), overtime_after_minutes: form.overtime === '' ? null : Number(form.overtime), active: true,
    }
    const ok = await run(() => editing
      ? api(`/roster/shifts/${editing}`, { method: 'PUT', body })
      : api('/roster/shifts', { body }), editing ? 'Shift updated' : 'Shift added')
    if (ok) {
      edit(null)
      reload()
    }
  }

  async function toggle(shift: Shift) {
    const body = { kind: shift.kind, name: shift.name, start_time: shift.start_time, end_time: shift.end_time, grace_minutes: shift.grace_minutes,
      break_minutes: shift.break_minutes, overtime_after_minutes: shift.overtime_after_minutes, active: !shift.active }
    if (await run(() => api(`/roster/shifts/${shift.id}`, { method: 'PUT', body }), shift.active ? 'Shift retired' : 'Shift restored')) reload()
  }

  return (
    <div className="space-y-4">
      <Table>
        <thead><tr><Th>Shift</Th><Th>Hours</Th><Th>Late after</Th><Th>Break</Th><Th>Overtime after</Th><Th /></tr></thead>
        <tbody>
          {data?.map((s) => (
            <tr key={s.id} className={s.active ? undefined : 'opacity-60'}>
              <Td className="font-medium">{s.name}{s.kind === 'weekoff' && <Badge className="ml-2">Week off</Badge>}{!s.active && <Badge className="ml-2">Retired</Badge>}</Td>
              {s.kind === 'weekoff' ? <Td colSpan={4}>Day off - not scheduled, not chased for check-in</Td> : <>
                <Td>{hhmm(s.start_time)} - {hhmm(s.end_time)}</Td>
                <Td>{s.grace_minutes} min</Td>
                <Td>{s.break_minutes} min</Td>
                <Td>{s.overtime_after_minutes == null ? 'Shift length' : `${s.overtime_after_minutes} min`}</Td>
              </>}
              <Td className="space-x-2 text-right">
                <Button size="sm" variant="outline" onClick={() => edit(s)}>Edit</Button>
                <Button size="sm" variant="outline" onClick={() => toggle(s)}>{s.active ? 'Retire' : 'Restore'}</Button>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Card>
        <CardHeader><CardTitle>{editing ? 'Edit shift' : 'Add shift'}</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={save} className="flex flex-wrap items-end gap-3">
            <Field label="Type">
              <Select value={form.kind} disabled={editing !== null} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="work">Working shift</option>
                <option value="weekoff">Week off</option>
              </Select>
            </Field>
            <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            {form.kind === 'work' && <>
            <Field label="Start"><Input type="time" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
            <Field label="End"><Input type="time" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
            <Field label="Late after (min)"><Input type="number" min={0} className="w-28" value={form.grace} onChange={(e) => setForm({ ...form, grace: e.target.value })} /></Field>
            <Field label="Break (min)"><Input type="number" min={0} className="w-28" value={form.brk} onChange={(e) => setForm({ ...form, brk: e.target.value })} /></Field>
            <Field label="Overtime after (min)"><Input type="number" min={0} className="w-32" value={form.overtime} onChange={(e) => setForm({ ...form, overtime: e.target.value })} /></Field>
            </>}
            <Button type="submit">{editing ? 'Save' : 'Add shift'}</Button>
            {editing && <Button type="button" variant="outline" onClick={() => edit(null)}>Cancel</Button>}
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
