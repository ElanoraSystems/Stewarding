import { useEffect, useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { api, uploadFile } from '@/lib/api'
import { label } from '@/lib/format'
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
  const [value, setValue] = useState('')
  const [reference, setReference] = useState('')
  const [comment, setComment] = useState('')
  const [action, setAction] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!prefill) return
    setEquipmentId(String(prefill.equipmentId))
    setScheduleId(String(prefill.scheduleId))
  }, [prefill])

  const selected = equipment.find((e) => String(e.id) === equipmentId)
  const schedules = selected?.schedules.filter((s) => s.active) ?? []
  const schedule = schedules.find((s) => String(s.id) === scheduleId)
  const result = verdict(value, schedule)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    const ok = await run(async () => {
      const evidence = file ? await uploadFile(file) : null
      await api('/monitoring/readings', {
        body: {
          equipment_id: Number(equipmentId), schedule_id: Number(scheduleId), value: Number(value), reference: reference || null,
          comment: comment || null, evidence_path: evidence, corrective_action: action || null,
          retest_of_id: prefill?.retestOf ?? null,
        },
      })
    }, result === 'fail' ? 'Failed check recorded - supervisor notified' : 'Check recorded')
    setBusy(false)
    if (ok) {
      setValue('')
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
            onChange={(e) => { setEquipmentId(e.target.value); setScheduleId('') }}>
            <option value="">Select monitoring point</option>
            {equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </Select>
        </Field>
        <Field label="Check">
          <Select required value={scheduleId} disabled={!!prefill?.retestOf} onChange={(e) => setScheduleId(e.target.value)}>
            <option value="">Select check</option>
            {schedules.map((s) => (
              <option key={s.id} value={s.id}>{label(s.stage)} - {s.source === 'independent_probe' ? 'probe' : 'machine display'}</option>
            ))}
          </Select>
        </Field>
      </div>
      {schedule && (
        <p className="text-sm text-ink-muted">
          {schedule.value_type === 'yes_no' ? `${schedule.parameter}: the answer must be Yes` : `${schedule.parameter}, acceptable range: ${schedule.min_value ?? 'no minimum'} to ${schedule.max_value ?? 'no maximum'} ${schedule.unit ?? ''}`}
          {schedule.source === 'independent_probe' ? ' (independent probe reading)' : ' (machine display reading)'}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        {schedule?.value_type === 'yes_no' ? (
          <Field label={schedule.parameter}>
            <Select required className="w-36" value={value} onChange={(e) => setValue(e.target.value)}>
              <option value="">Select</option>
              <option value="1">Yes</option>
              <option value="0">No</option>
            </Select>
          </Field>
        ) : (
          <Field label={schedule ? `${schedule.parameter}${schedule.unit ? ` (${schedule.unit})` : ''}` : 'Value'}>
            <Input required type="number" step="any" inputMode="decimal" className="w-36" value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
        )}
        {schedule && (schedule.require_reference || reference) && (
          <Field label="Batch, lot or product" hint={schedule.require_reference ? 'Required for this check.' : undefined}>
            <Input required={schedule.require_reference} maxLength={120} className="w-56" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        )}
        {result && <Badge tone={result === 'pass' ? 'ok' : 'critical'}>{result === 'pass' ? 'Within limits' : 'Out of range'}</Badge>}
      </div>
      {result === 'fail' && (
        <div className="space-y-2 rounded-md border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-medium text-danger">This check will be recorded as failed and your supervisor alerted.</p>
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
      <Button type="submit" className="w-full sm:w-auto" disabled={busy || !scheduleId || value === '' || (schedule?.require_reference && reference.trim() === '')}>
        {busy ? 'Saving...' : prefill?.retestOf ? 'Record retest' : 'Record check'}
      </Button>
    </form>
  )
}
