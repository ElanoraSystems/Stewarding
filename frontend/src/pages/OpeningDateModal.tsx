import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'

/** A manager moves an opening-stock line to another day so it counts in the right month. The stock itself does not change. */
export function OpeningDateModal({ txn, onClose, onDone }: { txn: { id: number; occurred_at: string } | null; onClose: () => void; onDone: () => void }) {
  const run = useRun()
  const [day, setDay] = useState('')
  const [reason, setReason] = useState('')
  const ready = day !== '' && reason.trim().length >= 5

  async function save() {
    if (txn && await run(() => api(`/inventory/transactions/${txn.id}/date`, { method: 'PUT', body: { new_date: day, reason: reason.trim() } }), 'Date changed')) {
      setDay('')
      setReason('')
      onDone()
      onClose()
    }
  }

  return (
    <Modal open={txn !== null} title="Change the date of opening stock" onClose={onClose} size="sm"
      description={txn ? `Now dated ${fmtDateTime(txn.occurred_at)}. It must come before the other movements of this item here. Quantities do not change; costs and month-end figures follow the new date.` : undefined}
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!ready} onClick={save}>Change the date</Button></>}>
      <div className="space-y-3">
        <Field label="New date"><Input aria-label="New date" type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
        <Field label="Reason (at least 5 characters)"><Input aria-label="Reason" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
