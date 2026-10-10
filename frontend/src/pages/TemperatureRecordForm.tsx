import { useEffect, useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { api, uploadFile } from '@/lib/api'
import { label } from '@/lib/format'
import { useRun } from '@/lib/toast'

export interface Schedule {
  id: number
  stage: string
  source: string
  timing: string
  min_temp_c: number | null
  max_temp_c: number | null
  time_of_day: string | null
  interval_minutes: number | null
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

function verdict(value: string, schedule?: Schedule): 'pass' | 'fail' | null {
  if (value === '' || !schedule) return null
  const temp = Number(value)
  const low = schedule.min_temp_c
  const high = schedule.max_temp_c
  return (low === null || temp >= low) && (high === null || temp <= high) ? 'pass' : 'fail'
}

export function TemperatureRecordForm({ equipment, prefill, onSaved, onClearRetest }: RecordFormProps) {
  const run = useRun()
  const [equipmentId, setEquipmentId] = useState('')
  const [scheduleId, setScheduleId] = useState('')
  const [temp, setTemp] = useState('')
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
  const result = verdict(temp, schedule)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    const ok = await run(async () => {
      const evidence = file ? await uploadFile(file) : null
      await api('/temperature/readings', {
        body: {
          equipment_id: Number(equipmentId), schedule_id: Number(scheduleId), temp_c: Number(temp),
          comment: comment || null, evidence_path: evidence, corrective_action: action || null,
          retest_of_id: prefill?.retestOf ?? null,
        },
      })
    }, result === 'fail' ? 'Failed reading recorded - supervisor notified' : 'Reading recorded')
    setBusy(false)
    if (ok) {
      setTemp('')
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
        <Field label="Equipment">
          <Select required value={equipmentId} disabled={!!prefill?.retestOf}
            onChange={(e) => { setEquipmentId(e.target.value); setScheduleId('') }}>
            <option value="">Select equipment</option>
            {equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </Select>
        </Field>
        <Field label="Monitoring stage">
          <Select required value={scheduleId} disabled={!!prefill?.retestOf} onChange={(e) => setScheduleId(e.target.value)}>
            <option value="">Select stage</option>
            {schedules.map((s) => (
              <option key={s.id} value={s.id}>{label(s.stage)} - {s.source === 'independent_probe' ? 'probe' : 'machine display'}</option>
            ))}
          </Select>
        </Field>
      </div>
      {schedule && (
        <p className="text-sm text-ink-muted">
          Acceptable range: {schedule.min_temp_c ?? 'no minimum'} to {schedule.max_temp_c ?? 'no maximum'} C
          {schedule.source === 'independent_probe' ? ' (independent probe reading)' : ' (machine display reading)'}
        </p>
      )}
      <div className="flex items-end gap-3">
        <Field label="Temperature (C)">
          <Input required type="number" step="0.1" inputMode="decimal" className="w-36" value={temp} onChange={(e) => setTemp(e.target.value)} />
        </Field>
        {result && <Badge tone={result === 'pass' ? 'ok' : 'critical'}>{result === 'pass' ? 'Within limits' : 'Out of range'}</Badge>}
      </div>
      {result === 'fail' && (
        <div className="space-y-2 rounded-md border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-medium text-danger">This reading will be recorded as failed and your supervisor alerted.</p>
          <Field label="Corrective action taken" hint="You can also add it afterwards from the open actions list.">
            <Input value={action} onChange={(e) => setAction(e.target.value)} />
          </Field>
        </div>
      )}
      <Field label="Comments (optional)"><Input value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
      <Field label="Photo evidence (optional)">
        <Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <Button type="submit" className="w-full sm:w-auto" disabled={busy || !scheduleId || temp === ''}>
        {busy ? 'Saving...' : prefill?.retestOf ? 'Record retest' : 'Record reading'}
      </Button>
    </form>
  )
}
