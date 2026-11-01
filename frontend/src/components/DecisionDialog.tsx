import { Check, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { cn } from '@/lib/utils'

export type Decision = 'approved' | 'rejected'

interface Props {
  open: boolean
  title: string
  /** What the decision is about, shown under the title: the task, the reading or the alert. */
  subject?: string
  /** Which choice is selected when it opens. */
  initial?: Decision
  /** Set when only approving makes sense, such as approving several at once. */
  approveOnly?: boolean
  onClose: () => void
  /** Return true once the decision is saved, so the dialog closes. */
  onDecide: (decision: Decision, comment: string) => Promise<boolean>
}

/** Approve or reject with a comment: optional when approving, at least five characters when rejecting. Both go to the approvals report. */
export function DecisionDialog({ open, title, subject, initial = 'approved', approveOnly = false, onClose, onDecide }: Props) {
  const [decision, setDecision] = useState<Decision>(initial)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (open) {
      setDecision(initial)
      setComment('')
    }
  }, [open, initial])
  const rejecting = decision === 'rejected'
  const tooShort = rejecting && comment.trim().length < 5

  async function submit() {
    setBusy(true)
    const ok = await onDecide(decision, comment.trim())
    setBusy(false)
    if (ok) setComment('')
  }

  return (
    <Modal open={open} size="md" title={title} description={subject} onClose={onClose}
      footer={<>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button variant={rejecting ? 'danger' : 'default'} disabled={tooShort || busy} onClick={submit}>{rejecting ? 'Reject' : 'Approve'}</Button>
      </>}>
      <div className="space-y-4">
        {!approveOnly && (
          <div role="radiogroup" aria-label="Decision" className="grid grid-cols-2 gap-2">
            {([['approved', 'Approve', Check], ['rejected', 'Reject', X]] as const).map(([value, text, Icon]) => (
              <button key={value} type="button" role="radio" aria-checked={decision === value} onClick={() => setDecision(value)}
                className={cn('flex items-center justify-center gap-2 rounded-xl border px-3 py-3 text-sm font-semibold transition-colors',
                  decision === value ? (value === 'approved' ? 'border-ok bg-ok/10 text-ok' : 'border-danger bg-danger/10 text-danger') : 'border-border text-ink-muted hover:bg-surface-muted')}>
                <Icon className="h-4 w-4" aria-hidden /> {text}
              </button>
            ))}
          </div>
        )}
        <label className="block space-y-1.5 text-sm font-medium">
          {rejecting ? 'Why are you rejecting it? (required)' : 'Comment (optional)'}
          <textarea value={comment} maxLength={300} rows={3} onChange={(e) => setComment(e.target.value)}
            className="w-full rounded-xl border border-border bg-surface px-3 py-2 text-base font-normal outline-none focus:border-brand focus:ring-2 focus:ring-brand/30" />
        </label>
        <p className="text-xs text-ink-muted">Your decision and comment are kept and shown in the Approvals and Rejections report.</p>
      </div>
    </Modal>
  )
}
