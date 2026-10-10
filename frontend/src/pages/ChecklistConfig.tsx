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
import { qs, useApi } from '@/lib/useApi'

interface Task {
  id: number
  description: string
  deadline_time: string | null
  priority: string
  requires_photo: boolean
  requires_reading: boolean
  requires_verification: boolean
  active: boolean
}
interface Template {
  id: number
  name: string
  category: string
  frequency: string
  active: boolean
  tasks: Task[]
}

interface ConfigProps {
  locationId: number | null
  onLocation: (id: number | null) => void
}

export function ChecklistConfig({ locationId, onLocation }: ConfigProps) {
  const run = useRun()
  const { data, reload } = useApi<Template[]>(locationId ? `/checklists/templates${qs({ location_id: locationId })}` : null)
  const [name, setName] = useState('')
  const [frequency, setFrequency] = useState('daily')
  const [taskText, setTaskText] = useState<Record<number, string>>({})
  const [removing, setRemoving] = useState<Task | null>(null)

  async function addTemplate(event: FormEvent) {
    event.preventDefault()
    const ok = await run(() => api('/checklists/templates', { body: { name, category: 'Cleaning', location_id: locationId, frequency } }), 'Template added')
    if (ok) {
      setName('')
      reload()
    }
  }

  async function addTask(templateId: number) {
    const description = taskText[templateId]?.trim()
    if (!description) return
    const ok = await run(() => api(`/checklists/templates/${templateId}/tasks`, { body: { description } }), 'Task added')
    if (ok) {
      setTaskText((t) => ({ ...t, [templateId]: '' }))
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
        <Field label="Frequency">
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
                  <span>{task.description}</span>
                  <span className="flex items-center gap-1">
                    {task.requires_verification && <Badge tone="warn">Verify</Badge>}
                    {task.requires_photo && <Badge>Photo</Badge>}
                    {task.requires_reading && <Badge>Reading</Badge>}
                    {task.active ? <Button size="sm" variant="outline" onClick={() => setRemoving(task)}>Deactivate</Button> : <Badge>Inactive</Badge>}
                  </span>
                </li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Input aria-label={`Add task to ${t.name}`} placeholder="New task description" value={taskText[t.id] ?? ''}
                onChange={(e) => setTaskText((v) => ({ ...v, [t.id]: e.target.value }))} />
              <Button onClick={() => addTask(t.id)}>Add</Button>
            </div>
          </CardContent>
        </Card>
      ))}
      <ConfirmDialog open={removing !== null} title="Deactivate task" message={`"${removing?.description}" will stop being generated. Past records are kept.`}
        confirmLabel="Deactivate" onConfirm={removeTask} onCancel={() => setRemoving(null)} />
    </div>
  )
}
