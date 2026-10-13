import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { blankField, optionList } from '@/lib/formFields'
import { FieldRestrictions } from '@/pages/FieldEditor'
import type { Schedule } from '@/pages/MonitoringRecordForm'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MEASURES = [['Temperature', '°C'], ['Concentration', 'ppm'], ['pH', ''], ['Time', 'min'], ['Humidity', '%']]

interface CheckFormProps {
  equipmentId: number
  schedule: Schedule | null
  onClose: () => void
  onSaved: () => void
}

export function CheckFormModal({ equipmentId, schedule, onClose, onSaved }: CheckFormProps) {
  const run = useRun()
  const [form, setForm] = useState({
    stage: schedule?.stage ?? '', parameter: schedule?.parameter ?? 'Temperature', unit: schedule?.unit ?? '°C',
    value_type: schedule?.value_type ?? 'number', source: schedule?.source ?? 'machine_display', timing: schedule?.timing ?? 'startup',
    time_of_day: schedule?.time_of_day?.slice(0, 5) ?? '', interval_minutes: schedule?.interval_minutes ? String(schedule.interval_minutes) : '',
    weekdays: schedule?.weekdays ?? [], day_of_month: schedule?.day_of_month ? String(schedule.day_of_month) : '',
    min_value: schedule?.min_value != null ? String(Number(schedule.min_value)) : '', max_value: schedule?.max_value != null ? String(Number(schedule.max_value)) : '',
    require_reference: schedule?.require_reference ?? false,
  })
  const [extra, setExtra] = useState({ options: (schedule?.options ?? []).join('\n'), fail: schedule?.fail_options ?? [], maxLength: String(schedule?.max_length ?? 200) })
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }))
  const isNumber = form.value_type === 'number'
  const toggleDay = (day: number) => set('weekdays', form.weekdays.includes(day) ? form.weekdays.filter((d) => d !== day) : [...form.weekdays, day])

  function pickMeasure(parameter: string) {
    const known = MEASURES.find(([name]) => name === parameter)
    setForm((f) => ({ ...f, parameter, unit: known ? known[1] : f.unit }))
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    const body = {
      stage: form.stage, parameter: form.parameter, unit: isNumber ? form.unit || null : null, value_type: form.value_type,
      require_reference: form.require_reference, source: form.source, timing: form.timing,
      time_of_day: form.time_of_day ? `${form.time_of_day}:00` : null,
      interval_minutes: form.timing === 'interval' ? Number(form.interval_minutes) : null,
      weekdays: form.weekdays.length ? form.weekdays : null, day_of_month: form.day_of_month ? Number(form.day_of_month) : null,
      min_value: isNumber && form.min_value !== '' ? Number(form.min_value) : null,
      max_value: isNumber && form.max_value !== '' ? Number(form.max_value) : null,
      options: form.value_type === 'choice' ? optionList(extra.options) : null,
      fail_options: form.value_type === 'choice' ? extra.fail.filter((o) => optionList(extra.options).includes(o)) : null,
      max_length: form.value_type === 'text' ? Number(extra.maxLength) : null,
    }
    const ok = await run(() => schedule
      ? api(`/equipment/schedules/${schedule.id}`, { method: 'PUT', body })
      : api(`/equipment/${equipmentId}/schedules`, { body }), 'Check saved')
    if (ok) onSaved()
  }

  return (
    <Modal open title={schedule ? 'Edit check' : 'Add check'} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        <p className="rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">Changes are audited and apply to new checks only.</p>
        <Field label="Check name" hint="For example Morning temperature, Core temperature, Sanitiser strength.">
          <Input required value={form.stage} onChange={(e) => set('stage', e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Answer type">
            <Select value={form.value_type} onChange={(e) => set('value_type', e.target.value as typeof form.value_type)}>
              <option value="number">A measurement (number)</option>
              <option value="yes_no">Yes or no</option>
              <option value="text">Short text</option>
              <option value="choice">Dropdown (choose one)</option>
            </Select>
          </Field>
          <Field label="What is checked">
            <Input list="measures" required value={form.parameter} onChange={(e) => pickMeasure(e.target.value)} />
            <datalist id="measures">{MEASURES.map(([name]) => <option key={name} value={name} />)}</datalist>
          </Field>
          {isNumber && <Field label="Unit"><Input maxLength={20} value={form.unit} onChange={(e) => set('unit', e.target.value)} /></Field>}
          {isNumber && <span />}
          {isNumber && <Field label="Minimum"><Input type="number" step="any" value={form.min_value} onChange={(e) => set('min_value', e.target.value)} /></Field>}
          {isNumber && <Field label="Maximum"><Input type="number" step="any" value={form.max_value} onChange={(e) => set('max_value', e.target.value)} /></Field>}
          <Field label="Reading source">
            <Select value={form.source} onChange={(e) => set('source', e.target.value)}>
              <option value="machine_display">Machine display</option>
              <option value="independent_probe">Independent probe</option>
            </Select>
          </Field>
          <Field label="Timing">
            <Select value={form.timing} onChange={(e) => set('timing', e.target.value)}>
              <option value="startup">At startup</option>
              <option value="checkpoint">At a set time</option>
              <option value="interval">Every few minutes</option>
            </Select>
          </Field>
          <Field label="First check at"><Input type="time" value={form.time_of_day} onChange={(e) => set('time_of_day', e.target.value)} /></Field>
          {form.timing === 'interval' && (
            <Field label="Every (minutes)"><Input required type="number" min={1} max={1440} value={form.interval_minutes} onChange={(e) => set('interval_minutes', e.target.value)} /></Field>
          )}
          <Field label="Day of month" hint="Leave blank unless it is monthly."><Input type="number" min={1} max={31} value={form.day_of_month} onChange={(e) => set('day_of_month', e.target.value)} /></Field>
        </div>
        {(form.value_type === 'text' || form.value_type === 'choice') && (
          <FieldRestrictions value={{ ...blankField(), type: form.value_type, ...extra }} onChange={(v) => setExtra({ options: v.options, fail: v.fail, maxLength: v.maxLength })} />
        )}
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Days (none selected means every day)</legend>
          <div className="flex flex-wrap gap-3">
            {DAYS.map((name, day) => (
              <label key={name} className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={form.weekdays.includes(day)} onChange={() => toggleDay(day)} /> {name}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.require_reference} onChange={(e) => set('require_reference', e.target.checked)} />
          Ask for a batch, lot or product reference (traceability)
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Modal>
  )
}
