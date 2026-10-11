import { useEffect, useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { api, uploadFile } from '@/lib/api'
import { label } from '@/lib/format'
import { cycleOf } from '@/lib/monitoring'
import { useRun } from '@/lib/toast'
import { useLookup } from '@/lib/useLookups'

export interface Schedule {
  id: number
  stage: string
  parameter: string
  unit: string | null
  value_type: 'number' | 'yes_no'
  require_reference: boolean
  source: string
  timing: string
  min_value: number | string | null
  max_value: number | string | null
  time_of_day: string | null
  interval_minutes: number | null
  weekdays: number[]
  day_of_month: number | null
  active: boolean
}

export interface EquipmentItem {
  id: number
  code: string
  name: string
  kind: string
  location_id: number
  status: string
  supervisor_id: number | null
  procedure_reference: string | null
  maintenance_notes: string | null
  schedules: Schedule[]
  needs_attention: boolean
  recent_failures: number
}

export interface Prefill {
  equipmentId: number
  scheduleId: number
  retestOf?: number
}

interface RecordFormProps {
  equipment: EquipmentItem[]
  prefill: Prefill | null
  onSaved: () => void
  onClearRetest: () => void
}

const num = (v: number | string | null) => (v === null ? null : Number(v))

function verdict(value: string, schedule?: Schedule): 'pass' | 'fail' | null {
  if (value === '' || !schedule) return null
  if (schedule.value_type === 'yes_no') return value === '1' ? 'pass' : 'fail'
  const amount = Number(value)
  const low = num(schedule.min_value)
  const high = num(schedule.max_value)
  return (low === null || amount >= low) && (high === null || amount <= high) ? 'pass' : 'fail'
}

export function MonitoringRecordForm({ equipment, prefill, onSaved, onClearRetest }: RecordFormProps) {
  const run = useRun()
  const standardActions = useLookup('corrective_action')
  const [equipmentId, setEquipmentId] = useState('')
  const [scheduleId, setScheduleId] = useState('')
  const [values, setValues] = useState<Record<number, string>>({})
  const [reference, setReference] = useState('')
  const [comment, setComment] = useState('')
  const [action, setAction] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!prefill) return
    setEquipmentId(String(prefill.equipmentId))
    setScheduleId(String(prefill.scheduleId))
    setValues({})
  }, [prefill])

  const selected = equipment.find((e) => String(e.id) === equipmentId)
  const schedules = selected?.schedules.filter((s) => s.active) ?? []
  const schedule = schedules.find((s) => String(s.id) === scheduleId)
  const cycle = schedule ? (prefill?.retestOf ? [schedule] : cycleOf(schedule, schedules)) : []
  const results = cycle.map((s) => verdict(values[s.id] ?? '', s))
  const anyFail = results.includes('fail')
  const complete = cycle.length > 0 && cycle.every((s) => (values[s.id] ?? '') !== '')
  const needsReference = cycle.some((s) => s.require_reference)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    const ok = await run(async () => {
      const evidence = file ? await uploadFile(file) : null
      const common = { comment: comment || null, evidence_path: evidence, corrective_action: action || null, reference: reference || null }
      if (prefill?.retestOf) {
        await api('/monitoring/readings', { body: { equipment_id: Number(equipmentId), schedule_id: Number(scheduleId), value: Number(values[Number(scheduleId)]), retest_of_id: prefill.retestOf, ...common } })
      } else {
        await api('/monitoring/readings/batch', { body: { equipment_id: Number(equipmentId), readings: cycle.map((s) => ({ schedule_id: s.id, value: Number(values[s.id]), ...common })) } })
      }
    }, anyFail ? 'Failed check recorded - supervisor notified' : cycle.length > 1 ? 'Checks recorded' : 'Check recorded')
    setBusy(false)
    if (ok) {
      setValues({})
      setReference('')
      setComment('')
      setAction('')
      setFile(null)
      onClearRetest()
      onSaved()
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {prefill?.retestOf && (
        <p className="flex items-center justify-between rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
          Retest of reading #{prefill.retestOf}
          <button type="button" className="underline" onClick={onClearRetest}>Cancel retest</button>
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Monitoring point">
          <Select required value={equipmentId} disabled={!!prefill?.retestOf}
            onChange={(e) => { setEquipmentId(e.target.value); setScheduleId(''); setValues({}) }}>
            <option value="">Select monitoring point</option>
            {equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </Select>
        </Field>
        <Field label="Check">
          <Select required value={scheduleId} disabled={!!prefill?.retestOf} onChange={(e) => { setScheduleId(e.target.value); setValues({}) }}>
            <option value="">Select check</option>
            {schedules.map((s) => (
              <option key={s.id} value={s.id}>{label(s.stage)} - {s.source === 'independent_probe' ? 'probe' : 'machine display'}</option>
            ))}
          </Select>
        </Field>
      </div>
      {cycle.length > 1 && <p className="text-sm text-ink-muted">These checks are due together, so enter all of them now: {cycle.map((s) => label(s.stage)).join(', ')}.</p>}
      <div className="space-y-3">
        {cycle.map((s, i) => (
          <div key={s.id} className="flex flex-wrap items-end gap-3">
            {s.value_type === 'yes_no' ? (
              <Field label={cycle.length > 1 ? `${label(s.stage)}: ${s.parameter}` : s.parameter}>
                <Select required className="w-36" value={values[s.id] ?? ''} onChange={(e) => setValues((v) => ({ ...v, [s.id]: e.target.value }))}>
                  <option value="">Select</option>
                  <option value="1">Yes</option>
                  <option value="0">No</option>
                </Select>
              </Field>
            ) : (
              <Field label={`${cycle.length > 1 ? `${label(s.stage)}: ` : ''}${s.parameter}${s.unit ? ` (${s.unit})` : ''}`}
                hint={`Acceptable ${s.min_value ?? 'no minimum'} to ${s.max_value ?? 'no maximum'} ${s.unit ?? ''}`}>
                <Input required type="number" step="any" inputMode="decimal" className="w-36" value={values[s.id] ?? ''} onChange={(e) => setValues((v) => ({ ...v, [s.id]: e.target.value }))} />
              </Field>
            )}
            {results[i] && <Badge tone={results[i] === 'pass' ? 'ok' : 'critical'}>{results[i] === 'pass' ? 'Within limits' : 'Out of range'}</Badge>}
          </div>
        ))}
        {needsReference && (
          <Field label="Batch, lot or product" hint="Required for this check.">
            <Input required maxLength={120} className="w-56" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        )}
      </div>
      {anyFail && (
        <div className="space-y-2 rounded-md border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-medium text-danger">A failed check will be recorded as failed and your supervisor alerted.</p>
          <Field label="Corrective action taken" hint="Pick a standard action or type your own. You can also add it afterwards from the open actions list.">
            <Input list="standard-actions" value={action} onChange={(e) => setAction(e.target.value)} />
            <datalist id="standard-actions">{standardActions.map((a) => <option key={a} value={a} />)}</datalist>
          </Field>
        </div>
      )}
      <Field label="Comments (optional)"><Input value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
      <Field label="Photo evidence (optional)">
        <Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <Button type="submit" className="w-full sm:w-auto" disabled={busy || !complete || (needsReference && reference.trim() === '')}>
        {busy ? 'Saving...' : prefill?.retestOf ? 'Record retest' : cycle.length > 1 ? 'Record all' : 'Record check'}
      </Button>
    </form>
  )
}
