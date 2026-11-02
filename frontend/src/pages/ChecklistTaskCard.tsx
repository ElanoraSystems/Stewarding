import { CheckCircle2, Clock, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { useTick } from '@/lib/useTick'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { SignedNumberInput } from '@/components/ui/signed-number-input'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { api, uploadFile } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useRun } from '@/lib/toast'
import { DecisionDialog, type Decision } from '@/components/DecisionDialog'
import type { EmployeeRow } from '@/pages/EmployeeForm'

export interface Instance {
  id: number
  task_id: number
  location_id: number
  local_date: string
  status: string
  effective_status: string
  due_at: string | null
  opens_at?: string | null
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
  template_name?: string
  waive_reason: string | null
}

type Dialog = 'complete' | 'waive' | 'assign' | null
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
  const [decide, setDecide] = useState<Decision | null>(null)
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

  const clock = useTick(!!item.opens_at)
  const notYet = !!item.opens_at && new Date(item.opens_at).getTime() > clock
  return (
    <div className={cn('border-l-4 px-4 py-3', status === 'overdue' || status === 'failed' ? 'border-l-danger bg-danger/5' : 'border-l-transparent')}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {selection && <input type="checkbox" aria-label={`Select ${item.description}`} checked={selection.checked} onChange={selection.onToggle} />}
        <div className="min-w-0 flex-1 basis-64">
          <p className="font-medium leading-snug">{item.description}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-ink-muted">
            <span className="flex items-center gap-1"><Clock className="h-3 w-3" aria-hidden /> Due {fmtTime(item.due_at, timezone)}</span>
            {item.requires_verification && <span>Needs approval</span>}
            {(item.priority === 'high' || item.priority === 'critical') && <span className="font-medium text-warn">{item.priority} priority</span>}
          </p>
        </div>
        <StatusBadge status={status} />
        <div className="flex flex-wrap items-center gap-2">
          {open && can('checklist.complete') && (
            notYet
              ? <Button size="sm" disabled><Clock className="h-4 w-4" /> Opens at {fmtTime(item.opens_at!, timezone)}</Button>
              : <Button size="sm" onClick={() => setDialog('complete')}><CheckCircle2 className="h-4 w-4" /> Complete</Button>
          )}
          {status === 'pending_verification' && can('checklist.verify') && item.completed_by !== me?.id && (
            <>
              <Button size="sm" onClick={() => setDecide('approved')}>Approve</Button>
              <Button size="sm" variant="outline" className="text-danger" onClick={() => setDecide('rejected')}>Reject</Button>
            </>
          )}
          {!FINISHED.includes(status) && can('checklist.verify') && (
            <Button size="sm" variant="ghost" onClick={() => setDialog('waive')}>Waive</Button>
          )}
          {open && can('task.assign') && (
            <Button size="sm" variant="ghost" onClick={() => setDialog('assign')}><UserPlus className="h-4 w-4" /> Assign</Button>
          )}
        </div>
      </div>
      {item.instructions && <p className="mt-1 text-sm text-ink-muted">{item.instructions}</p>}
      {item.comment && <p className="mt-2 whitespace-pre-line rounded bg-surface-muted p-2 text-sm">{item.comment}</p>}
      {item.waive_reason && <p className="mt-1 text-sm text-ink-muted">Waived: {item.waive_reason}</p>}

      <Modal open={dialog === 'complete'} title={item.description} onClose={() => setDialog(null)}>
        <div className="space-y-3">
          {item.requires_reading && <Field label="Reading"><SignedNumberInput value={reading} onChange={setReading} /></Field>}
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

      <DecisionDialog open={decide !== null} initial={decide ?? 'approved'} title="Approve or reject" subject={item.description} onClose={() => setDecide(null)}
        onDecide={async (decision, note) => {
          const ok = await run(() => api(`${base}/verify`, { body: { approve: decision === 'approved', comment: note || null } }), decision === 'approved' ? 'Task approved' : 'Task rejected')
          if (ok) {
            setDecide(null)
            onChanged()
          }
          return ok
        }} />

      <Modal open={dialog === 'waive'} title="Waive task" onClose={() => setDialog(null)}>
        <div className="space-y-3">
          <Field label="Reason for waiving">
            <Input value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant="danger" disabled={comment.trim().length < 5}
              onClick={() => act('waive', { reason: comment }, 'Task waived')}>
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
    </div>
  )
}
