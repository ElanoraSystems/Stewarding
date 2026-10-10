import { Plus, Wrench } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { EquipmentItem, Schedule } from '@/pages/TemperatureRecordForm'

interface ScheduleForm {
  id: number | null
  stage: string
  source: string
  timing: string
  time_of_day: string
  interval_minutes: string
  min_temp_c: string
  max_temp_c: string
}

const EMPTY: ScheduleForm = { id: null, stage: '', source: 'machine_display', timing: 'startup', time_of_day: '', interval_minutes: '', min_temp_c: '', max_temp_c: '' }

export function EquipmentPage({ embedded = false }: { embedded?: boolean }) {
  const { me } = useAuth()
  const run = useRun()
  const canManage = me?.permissions.includes('equipment.manage') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const { data, reload } = useApi<EquipmentItem[]>(locationId ? `/equipment${qs({ location_id: locationId })}` : null)
  const [editing, setEditing] = useState<{ equipmentId: number; form: ScheduleForm } | null>(null)
  const [adding, setAdding] = useState(false)
  const [newEq, setNewEq] = useState({ code: '', name: '', kind: 'dishwasher', manufacturer: '', model: '' })

  async function saveSchedule(event: FormEvent) {
    event.preventDefault()
    if (!editing) return
    const { form, equipmentId } = editing
    const body = {
      stage: form.stage, source: form.source, timing: form.timing,
      time_of_day: form.time_of_day ? `${form.time_of_day}:00` : null,
      interval_minutes: form.interval_minutes ? Number(form.interval_minutes) : null,
      min_temp_c: form.min_temp_c === '' ? null : Number(form.min_temp_c),
      max_temp_c: form.max_temp_c === '' ? null : Number(form.max_temp_c),
    }
    const ok = await run(() => form.id
      ? api(`/equipment/schedules/${form.id}`, { method: 'PUT', body })
      : api(`/equipment/${equipmentId}/schedules`, { body }), 'Monitoring stage saved')
    if (ok) {
      setEditing(null)
      reload()
    }
  }

  async function setStatus(eq: EquipmentItem, status: string) {
    if (await run(() => api(`/equipment/${eq.id}`, { method: 'PUT', body: { status } }), 'Status updated')) reload()
  }

  async function addEquipment(event: FormEvent) {
    event.preventDefault()
    const ok = await run(() => api('/equipment', { body: { ...newEq, location_id: locationId, manufacturer: newEq.manufacturer || null, model: newEq.model || null } }), 'Equipment added')
    if (ok) {
      setAdding(false)
      reload()
    }
  }

  const openEdit = (equipmentId: number, s?: Schedule) => setEditing({
    equipmentId,
    form: s ? {
      id: s.id, stage: s.stage, source: s.source, timing: s.timing, time_of_day: s.time_of_day?.slice(0, 5) ?? '',
      interval_minutes: s.interval_minutes ? String(s.interval_minutes) : '', min_temp_c: s.min_temp_c?.toString() ?? '', max_temp_c: s.max_temp_c?.toString() ?? '',
    } : EMPTY,
  })
  const setField = (key: keyof ScheduleForm, value: string) => setEditing((e) => e && { ...e, form: { ...e.form, [key]: value } })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {embedded ? <h2 className="text-lg font-semibold">Equipment and monitoring schedules</h2> : <h1 className="text-2xl font-semibold">Equipment Management</h1>}
        <div className="flex gap-3">
          <LocationSelect value={locationId} onChange={setLocationId} />
          {canManage && <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add equipment</Button>}
        </div>
      </div>
      <p className="text-sm text-ink-muted">
        Each machine has one or more monitoring stages. A stage sets what is measured (machine display or independent probe),
        when it is checked (at startup, every N minutes, or at a shift checkpoint) and the acceptable temperature range.
        Limits must come from the manufacturer's instructions and the approved food-safety procedure.
        {!embedded && canManage && ' Managers can also edit these under Settings, Monitoring schedules.'}
      </p>

      {data?.length === 0 && <EmptyState title="No equipment at this location" />}
      {data?.map((eq) => (
        <Card key={eq.id} className={eq.needs_attention ? 'border-warn/60' : undefined}>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <Wrench className="h-4 w-4 text-brand" aria-hidden /> {eq.name}
              <span className="text-sm font-normal text-ink-muted">{eq.code} - {label(eq.kind)}</span>
              <StatusBadge status={eq.status} />
              {eq.needs_attention && <Badge tone="warn">Needs attention ({eq.recent_failures} recent failures)</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {eq.maintenance_notes && <p className="text-sm text-ink-muted">{eq.maintenance_notes}</p>}
            {canManage && (
              <Select aria-label={`Status of ${eq.name}`} className="w-auto" value={eq.status} onChange={(e) => setStatus(eq, e.target.value)}>
                <option value="operational">Operational</option>
                <option value="attention">Needs attention</option>
                <option value="out_of_service">Out of service</option>
              </Select>
            )}
            <Table>
              <thead><tr><Th>Stage</Th><Th>Source</Th><Th>When</Th><Th>Limits (C)</Th>{canManage && <Th />}</tr></thead>
              <tbody>
                {eq.schedules.map((s) => (
                  <tr key={s.id}>
                    <Td>{label(s.stage)}</Td>
                    <Td>{s.source === 'independent_probe' ? 'Independent probe' : 'Machine display'}</Td>
                    <Td>{label(s.timing)}{s.timing === 'interval' && ` every ${s.interval_minutes} min`}{s.time_of_day && ` from ${s.time_of_day.slice(0, 5)}`}</Td>
                    <Td>{s.min_temp_c ?? '-'} to {s.max_temp_c ?? '-'}</Td>
                    {canManage && <Td><Button size="sm" variant="outline" onClick={() => openEdit(eq.id, s)}>Edit limits</Button></Td>}
                  </tr>
                ))}
              </tbody>
            </Table>
            {canManage && <Button size="sm" variant="outline" onClick={() => openEdit(eq.id)}>Add monitoring stage</Button>}
          </CardContent>
        </Card>
      ))}

      <Modal open={editing !== null} title={editing?.form.id ? 'Edit monitoring stage' : 'Add monitoring stage'} onClose={() => setEditing(null)}>
        {editing && (
          <form onSubmit={saveSchedule} className="space-y-3">
            <p className="rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">Limit changes are audited and apply to new readings only.</p>
            <Field label="Stage (e.g. wash, final_rinse)"><Input required value={editing.form.stage} onChange={(e) => setField('stage', e.target.value)} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Reading source">
                <Select value={editing.form.source} onChange={(e) => setField('source', e.target.value)}>
                  <option value="machine_display">Machine display</option>
                  <option value="independent_probe">Independent probe</option>
                </Select>
              </Field>
              <Field label="Timing">
                <Select value={editing.form.timing} onChange={(e) => setField('timing', e.target.value)}>
                  <option value="startup">At startup</option>
                  <option value="interval">At intervals</option>
                  <option value="checkpoint">Shift checkpoint</option>
                </Select>
              </Field>
              <Field label="First check at"><Input type="time" value={editing.form.time_of_day} onChange={(e) => setField('time_of_day', e.target.value)} /></Field>
              {editing.form.timing === 'interval' && (
                <Field label="Every (minutes)"><Input required type="number" min={1} value={editing.form.interval_minutes} onChange={(e) => setField('interval_minutes', e.target.value)} /></Field>
              )}
              <Field label="Minimum (C)"><Input type="number" step="0.1" value={editing.form.min_temp_c} onChange={(e) => setField('min_temp_c', e.target.value)} /></Field>
              <Field label="Maximum (C)"><Input type="number" step="0.1" value={editing.form.max_temp_c} onChange={(e) => setField('max_temp_c', e.target.value)} /></Field>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
              <Button type="submit">Save</Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={adding} title="Add equipment" onClose={() => setAdding(false)}>
        <form onSubmit={addEquipment} className="space-y-3">
          <Field label="Equipment ID"><Input required value={newEq.code} onChange={(e) => setNewEq({ ...newEq, code: e.target.value })} /></Field>
          <Field label="Name"><Input required value={newEq.name} onChange={(e) => setNewEq({ ...newEq, name: e.target.value })} /></Field>
          <Field label="Type">
            <Select value={newEq.kind} onChange={(e) => setNewEq({ ...newEq, kind: e.target.value })}>
              <option value="dishwasher">Dishwasher</option>
              <option value="glasswasher">Glasswasher</option>
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Manufacturer"><Input value={newEq.manufacturer} onChange={(e) => setNewEq({ ...newEq, manufacturer: e.target.value })} /></Field>
            <Field label="Model"><Input value={newEq.model} onChange={(e) => setNewEq({ ...newEq, model: e.target.value })} /></Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setAdding(false)}>Cancel</Button>
            <Button type="submit">Add</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
