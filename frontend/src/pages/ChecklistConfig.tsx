import { useState, type FormEvent } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState } from '@/components/ui/table'
import { api } from '@/lib/api'
import { label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { useLookup } from '@/lib/useLookups'
import { qs, useApi } from '@/lib/useApi'
import { ChecklistTaskModal, type ConfigTask } from '@/pages/ChecklistTaskModal'

interface Template {
  id: number
  name: string
  category: string
  frequency: string
  active: boolean
  tasks: ConfigTask[]
}

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const daysOf = (weekdays: string) => (weekdays.split(',').length === 7 ? 'Every day' : weekdays.split(',').map((d) => DAY_NAMES[Number(d)]).join(', '))

interface ConfigProps {
  locationId: number | null
  onLocation: (id: number | null) => void
}

export function ChecklistConfig({ locationId, onLocation }: ConfigProps) {
  const run = useRun()
  const { data, reload } = useApi<Template[]>(locationId ? `/checklists/templates${qs({ location_id: locationId })}` : null)
  const categories = useLookup('checklist_category')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [frequency, setFrequency] = useState('daily')
  const [editing, setEditing] = useState<{ templateId: number; frequency: string; task: ConfigTask | null } | null>(null)
  const [removing, setRemoving] = useState<ConfigTask | null>(null)

  async function addTemplate(event: FormEvent) {
    event.preventDefault()
    const ok = await run(() => api('/checklists/templates', { body: { name, category: category || categories[0] || 'General', location_id: locationId, frequency } }), 'Template added')
    if (ok) {
      setName('')
      reload()
    }
  }

  async function removeTask() {
    if (!removing) return
    const ok = await run(() => api(`/checklists/tasks/${removing.id}`, { method: 'DELETE' }), 'Task deactivated')
    setRemoving(null)
    if (ok) reload()
  }

  async function applyStarter() {
    const ok = await run(() => api('/checklists/starter', { body: { location_id: locationId } }), 'Starter templates applied')
    if (ok) reload()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <LocationSelect value={locationId} onChange={onLocation} />
        <Button variant="outline" onClick={applyStarter}>Apply starter templates</Button>
      </div>

      <form onSubmit={addTemplate} className="flex flex-wrap items-end gap-3">
        <Field label="New template name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Category">
          <Select value={category || categories[0] || ''} onChange={(e) => setCategory(e.target.value)}>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
        </Field>
        <Field label="Frequency" hint="Sets the default days for new tasks; each task can repeat on any days.">
          <Select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="per_shift">Once per shift</option>
            <option value="custom">Custom</option>
          </Select>
        </Field>
        <Button type="submit">Add template</Button>
      </form>

      {data?.length === 0 && <EmptyState title="No templates at this location" hint="Apply the starter templates or add your own." />}
      {data?.map((t) => (
        <Card key={t.id}>
          <CardHeader><CardTitle className="flex items-center gap-2">{t.name} <Badge>{label(t.frequency)}</Badge></CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <ul className="divide-y divide-border text-sm">
              {t.tasks.map((task) => (
                <li key={task.id} className={`flex flex-wrap items-center justify-between gap-2 py-2 ${task.active ? '' : 'opacity-50'}`}>
                  <span>{task.description}<span className="ml-2 text-xs text-ink-muted">{daysOf(task.weekdays)}</span></span>
                  <span className="flex items-center gap-1">
                    {task.requires_verification && <Badge tone="warn">Verify</Badge>}
                    {task.requires_photo && <Badge>Photo</Badge>}
                    {task.requires_reading && <Badge>Reading</Badge>}
                    <Button size="sm" variant="outline" onClick={() => setEditing({ templateId: t.id, frequency: t.frequency, task })}>Edit</Button>
                    {task.active ? <Button size="sm" variant="outline" onClick={() => setRemoving(task)}>Deactivate</Button> : <Badge>Inactive</Badge>}
                  </span>
                </li>
              ))}
            </ul>
            <Button size="sm" variant="outline" onClick={() => setEditing({ templateId: t.id, frequency: t.frequency, task: null })}>Add task</Button>
          </CardContent>
        </Card>
      ))}
      {editing && <ChecklistTaskModal templateId={editing.templateId} templateFrequency={editing.frequency} task={editing.task} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
      <ConfirmDialog open={removing !== null} title="Deactivate task" message={`"${removing?.description}" will stop being generated. Past records are kept.`}
        confirmLabel="Deactivate" onConfirm={removeTask} onCancel={() => setRemoving(null)} />
    </div>
  )
}
