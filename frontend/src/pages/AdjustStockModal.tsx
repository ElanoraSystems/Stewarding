import { useState } from 'react'
import { ItemPicker } from '@/components/ItemPicker'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useAllItems } from '@/lib/useItems'

/** A manager corrects what the books hold for one item in one location. The old lines stay in the history; the correction is added to them. */
export function AdjustStockModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const run = useRun()
  const { items } = useAllItems()
  const [itemId, setItemId] = useState('')
  const [locationId, setLocationId] = useState<number | null>(null)
  const [correct, setCorrect] = useState('')
  const [reason, setReason] = useState('')

  const item = items.find((i) => String(i.id) === itemId)
  const have = item && locationId !== null ? item.by_location[String(locationId)] ?? 0 : null
  const change = have !== null && correct !== '' ? Number(correct) - have : null
  const ready = change !== null && change !== 0 && reason.trim().length >= 5

  async function save() {
    if (!item || locationId === null || change === null) return
    const body = { item_id: item.id, location_id: locationId, txn_type: 'adjustment', qty: change, reason: reason.trim() }
    if (await run(() => api('/inventory/transactions', { body }), 'Stock adjusted')) {
      setItemId('')
      setCorrect('')
      setReason('')
      onDone()
      onClose()
    }
  }

  return (
    <Modal open={open} title="Adjust stock" onClose={onClose} size="md"
      description="Enter what the stock should be. The difference is added to the history as an adjustment; earlier lines are not changed."
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!ready} onClick={save}>Post the adjustment</Button></>}>
      <div className="space-y-3">
        <Field label="Item"><ItemPicker items={items} value={itemId} onChange={setItemId} label="Item" /></Field>
        <Field label="Location"><LocationSelect value={locationId} onChange={setLocationId} className="w-full" /></Field>
        <Field label={`Stock should be${item ? ` (${item.unit})` : ''}`}>
          <Input aria-label="Stock should be" type="number" min={0} inputMode="numeric" value={correct} onChange={(e) => setCorrect(e.target.value)} />
        </Field>
        {have !== null && <p className="text-sm text-ink-muted" aria-live="polite">
          The books hold {have} here now.{change !== null && (change === 0 ? ' Nothing to change.' : ` This posts ${change > 0 ? '+' : ''}${change}.`)}</p>}
        <Field label="Reason (at least 5 characters)"><Input aria-label="Reason" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
