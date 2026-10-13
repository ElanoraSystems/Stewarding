import { CheckCircle2, Clock, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { api, uploadFile } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import type { EmployeeRow } from '@/pages/EmployeeForm'

export interface Instance {
  id: number
  task_id: number
  location_id: number
  local_date: string
  status: string
  effective_status: string
  due_at: string | null
  assigned_employee_id: number | null
  completed_by: number | null
  comment: string | null
  description: string
  instructions: string | null
  priority: string
  requires_photo: boolean
  requires_reading: boolean
  requires_verification: boolean
  category: string
  frequency: string
  waive_reason: string | null
}

type Dialog = 'complete' | 'reject' | 'waive' | 'assign' | null
const FINISHED = ['completed', 'verified', 'waived']

interface TaskCardProps {
  item: Instance
  timezone?: string
  staff: EmployeeRow[]
  onChanged: () => void
  selection?: { checked: boolean; onToggle: () => void }
}

export function ChecklistTaskCard({ item, timezone, staff, onChanged, selection }: TaskCardProps) {
  const { me } = useAuth()
  const run = useRun()
  const can = (permission: string) => me?.permissions.includes(permission) ?? false
  const [dialog, setDialog] = useState<Dialog>(null)
  const [comment, setComment] = useState('')
  const [reading, setReading] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [assignee, setAssignee] = useState('')
  const status = item.effective_status
  const open = !FINISHED.includes(status) && status !== 'pending_verification'
  const base = `/checklists/instances/${item.id}`

  async function act(path: string, body: unknown, success: string) {
    const ok = await run(() => api(`${base}/${path}`, { body }), success)
    if (ok) {
      setDialog(null)
      setComment('')
      onChanged()
    }
  }

  async function complete() {
    const ok = await run(async () => {
      const evidence = file ? await uploadFile(file) : null
      await api(`${base}/complete`, { body: { comment: comment || null, reading: reading === '' ? null : Number(reading), evidence_path: evidence } })
    }, 'Task submitted')
    if (ok) {
      setDialog(null)
      setComment('')
      setReading('')
      setFile(null)
      onChanged()
    }
  }

  return (
    <Card className={status === 'overdue' || status === 'failed' ? 'border-danger/50' : undefined}>
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-start gap-3">
            {selection && <input type="checkbox" className="mt-1" aria-label={`Select ${item.description}`} checked={selection.checked} onChange={selection.onToggle} />}
            <div>
            <p className="font-medium">{item.description}</p>
            <p className="flex items-center gap-1 text-xs text-ink-muted">
              <Clock className="h-3 w-3" aria-hidden /> Due {fmtTime(item.due_at, timezone)}
              {item.requires_verification && ' - needs verification'}
            </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {(item.priority === 'high' || item.priority === 'critical') && <Badge tone="warn">{item.priority}</Badge>}
            <StatusBadge status={status} />
          </div>
        </div>
        {item.instructions && <p className="text-sm text-ink-muted">{item.instructions}</p>}
        {item.comment && <p className="whitespace-pre-line rounded bg-surface-muted p-2 text-sm">{item.comment}</p>}
        {item.waive_reason && <p className="text-sm text-ink-muted">Waived: {item.waive_reason}</p>}

        <div className="flex flex-wrap gap-2">
          {open && can('checklist.complete') && (
            <Button size="sm" onClick={() => setDialog('complete')}><CheckCircle2 className="h-4 w-4" /> Complete</Button>
          )}
          {status === 'pending_verification' && can('checklist.verify') && item.completed_by !== me?.id && (
            <>
              <Button size="sm" onClick={() => act('verify', { approve: true }, 'Task verified')}>Approve</Button>
              <Button size="sm" variant="danger" onClick={() => setDialog('reject')}>Reject</Button>
            </>
          )}
          {!FINISHED.includes(status) && can('checklist.verify') && (
            <Button size="sm" variant="outline" onClick={() => setDialog('waive')}>Waive</Button>
          )}
          {open && can('task.assign') && (
            <Button size="sm" variant="outline" onClick={() => setDialog('assign')}><UserPlus className="h-4 w-4" /> Assign</Button>
          )}
        </div>
      </div>

      <Modal open={dialog === 'complete'} title={item.description} onClose={() => setDialog(null)}>
        <div className="space-y-3">
          {item.requires_reading && <Field label="Reading"><Input type="number" step="any" value={reading} onChange={(e) => setReading(e.target.value)} /></Field>}
          {item.requires_photo && (
            <Field label="Photo evidence">
              <Input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Field>
          )}
          <Field label="Comment (optional)"><Input value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button onClick={complete}>Submit</Button>
          </div>
        </div>
      </Modal>

      <Modal open={dialog === 'reject' || dialog === 'waive'} title={dialog === 'reject' ? 'Reject work' : 'Waive task'} onClose={() => setDialog(null)}>
        <div className="space-y-3">
          <Field label={dialog === 'reject' ? 'What needs redoing?' : 'Reason for waiving'}>
            <Input value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant="danger" disabled={comment.trim().length < 5}
              onClick={() => dialog === 'reject' ? act('verify', { approve: false, comment }, 'Task rejected') : act('waive', { reason: comment }, 'Task waived')}>
              Confirm
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={dialog === 'assign'} title="Assign task" onClose={() => setDialog(null)}>
        <div className="space-y-3">
          <Field label="Employee">
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">Select</option>
              {staff.filter((s) => s.location_ids.includes(item.location_id)).map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
            </Select>
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button disabled={!assignee} onClick={() => act('assign', { employee_id: Number(assignee) }, 'Task assigned')}>Assign</Button>
          </div>
        </div>
      </Modal>
    </Card>
  )
}
