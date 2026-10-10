import { useState, type FormEvent } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { api, uploadFile } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useAllItems } from '@/lib/useItems'
import { useLookup } from '@/lib/useLookups'

const OTHER = '__other__'

export function BreakageReportForm({ onSaved }: { onSaved: () => void }) {
  const run = useRun()
  const { items } = useAllItems()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [itemId, setItemId] = useState('')
  const [qty, setQty] = useState('1')
  const [type, setType] = useState('breakage')
  const reasons = useLookup('breakage_reason')
  const [reasonChoice, setReasonChoice] = useState('')
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const ok = await run(async () => {
      const photo = file ? await uploadFile(file) : null
      await api('/breakage', { body: {
        location_id: locationId, item_id: Number(itemId), qty: Number(qty), incident_type: type,
        reason: reason || null, description: description || null, photo_path: photo,
      } })
    }, 'Incident reported - your supervisor has been notified')
    if (ok) {
      setItemId('')
      setQty('1')
      setReasonChoice('')
      setReason('')
      setDescription('')
      setFile(null)
      onSaved()
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Location"><LocationSelect className="w-full" value={locationId} onChange={setLocationId} /></Field>
        <Field label="Incident type">
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="breakage">Breakage</option>
            <option value="damage">Damage</option>
            <option value="missing">Missing</option>
            <option value="written_off">Written off</option>
          </Select>
        </Field>
        <Field label="Item">
          <Select required value={itemId} onChange={(e) => setItemId(e.target.value)}>
            <option value="">Select item</option>
            {items.map((i) => <option key={i.id} value={i.id}>{i.code} - {i.name}</option>)}
          </Select>
        </Field>
        <Field label="Quantity"><Input required type="number" min={1} inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
      </div>
      <Field label="What happened?">
        <Select value={reasonChoice} onChange={(e) => { setReasonChoice(e.target.value); if (e.target.value !== OTHER) setReason(e.target.value) }}>
          <option value="">Select a reason</option>
          {reasons.map((r) => <option key={r} value={r}>{r}</option>)}
          <option value={OTHER}>Other (describe)</option>
        </Select>
      </Field>
      {reasonChoice === OTHER && <Field label="Describe the cause"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
      <Field label="Description (optional)"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <Field label="Photo (optional)"><Input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
      <Button type="submit" className="w-full sm:w-auto" disabled={!locationId || !itemId || Number(qty) < 1}>Report incident</Button>
    </form>
  )
}
