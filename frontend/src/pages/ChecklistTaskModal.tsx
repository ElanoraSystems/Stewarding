import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'

export interface ConfigTask {
  id: number
  description: string
  instructions: string | null
  shift_id: number | null
  assigned_role: string | null
  assigned_employee_id: number | null
  scheduled_time: string | null
  deadline_time: string | null
  weekdays: string
  priority: string
  requires_photo: boolean
  requires_reading: boolean
  requires_verification: boolean
  mandatory_for_checkout: boolean
  escalation_minutes: number | null
  active_from: string | null
  active_to: string | null
  active: boolean
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]

interface TaskModalProps {
  templateId: number
  templateFrequency: string
  task: ConfigTask | null
  onClose: () => void
  onSaved: () => void
}

/** Adds or edits one task: what to do, which days it repeats on, its times and what completing it needs. */
export function ChecklistTaskModal({ templateId, templateFrequency, task, onClose, onSaved }: TaskModalProps) {
  const run = useRun()
  const [form, setForm] = useState({
    description: task?.description ?? '',
    instructions: task?.instructions ?? '',
    days: task ? task.weekdays.split(',').map(Number) : templateFrequency === 'weekly' ? [] : EVERY_DAY,
    scheduled_time: task?.scheduled_time?.slice(0, 5) ?? '',
    deadline_time: task?.deadline_time?.slice(0, 5) ?? '',
    priority: task?.priority ?? 'normal',
    requires_photo: task?.requires_photo ?? false,
    requires_reading: task?.requires_reading ?? false,
    requires_verification: task?.requires_verification ?? false,
    mandatory_for_checkout: task?.mandatory_for_checkout ?? true,
  })
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }))
  const toggle = (day: number) => set('days', form.days.includes(day) ? form.days.filter((d) => d !== day) : [...form.days, day].sort())
  const summary = form.days.length === 7 ? 'Every day' : form.days.length === 0 ? 'Choose at least one day' : form.days.map((d) => DAYS[d]).join(', ')

  async function save(event: FormEvent) {
    event.preventDefault()
    const body = {
      description: form.description.trim(), instructions: form.instructions.trim() || null,
      shift_id: task?.shift_id ?? null, assigned_role: task?.assigned_role ?? null, assigned_employee_id: task?.assigned_employee_id ?? null,
      escalation_minutes: task?.escalation_minutes ?? null, active_from: task?.active_from ?? null, active_to: task?.active_to ?? null,
      scheduled_time: form.scheduled_time ? `${form.scheduled_time}:00` : null, deadline_time: form.deadline_time ? `${form.deadline_time}:00` : null,
      weekdays: form.days.join(','), priority: form.priority, requires_photo: form.requires_photo, requires_reading: form.requires_reading,
      requires_verification: form.requires_verification, mandatory_for_checkout: form.mandatory_for_checkout,
    }
    const ok = await run(() => (task
      ? api(`/checklists/tasks/${task.id}`, { method: 'PUT', body: { ...body, active: task.active } })
      : api(`/checklists/templates/${templateId}/tasks`, { body })), task ? 'Task updated' : 'Task added')
    if (ok) onSaved()
  }

  return (
    <Modal open title={task ? 'Edit task' : 'Add task'} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        <Field label="Task"><Input required minLength={3} maxLength={300} value={form.description} onChange={(e) => set('description', e.target.value)} /></Field>
        <Field label="Instructions (optional)"><Input value={form.instructions} onChange={(e) => set('instructions', e.target.value)} /></Field>
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Repeats on</legend>
          <div className="flex flex-wrap items-center gap-3">
            {DAYS.map((name, day) => (
              <label key={name} className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={form.days.includes(day)} onChange={() => toggle(day)} /> {name}
              </label>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => set('days', EVERY_DAY)}>Every day</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => set('days', [0, 1, 2, 3, 4])}>Weekdays</Button>
            <span className="text-xs text-ink-muted">{summary}</span>
          </div>
        </fieldset>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Starts at"><Input type="time" value={form.scheduled_time} onChange={(e) => set('scheduled_time', e.target.value)} /></Field>
          <Field label="Due by"><Input type="time" value={form.deadline_time} onChange={(e) => set('deadline_time', e.target.value)} /></Field>
          <Field label="Priority">
            <Select value={form.priority} onChange={(e) => set('priority', e.target.value)}>
              {['low', 'normal', 'high', 'critical'].map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </Field>
        </div>
        <div className="space-y-1 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.requires_verification} onChange={(e) => set('requires_verification', e.target.checked)} /> A supervisor must verify it</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.requires_photo} onChange={(e) => set('requires_photo', e.target.checked)} /> Needs a photo</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.requires_reading} onChange={(e) => set('requires_reading', e.target.checked)} /> Needs a reading</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.mandatory_for_checkout} onChange={(e) => set('mandatory_for_checkout', e.target.checked)} /> Must be done before check-out</label>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={form.days.length === 0}>Save</Button>
        </div>
      </form>
    </Modal>
  )
}
