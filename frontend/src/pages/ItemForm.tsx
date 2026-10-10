import { AlertTriangle } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { Item } from '@/lib/useItems'

interface ItemFormProps {
  item: Item | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}

interface Similar {
  id: number
  code: string
  name: string
  active: boolean
}

export function ItemForm({ item, open, onClose, onSaved }: ItemFormProps) {
  const { me } = useAuth()
  const run = useRun()
  const editing = item !== null
  const categories = useApi<{ id: number; name: string }[]>('/inventory/categories')
  const units = useApi<{ id: number; name: string }[]>('/inventory/units')
  const suppliers = useApi<{ id: number; name: string }[]>('/suppliers')
  const [similar, setSimilar] = useState<Similar[]>([])
  const [form, setForm] = useState({
    name: item?.name ?? '', category_id: item ? String(item.category_id) : '',
    unit_id: item ? String(item.unit_id) : '', supplier_id: item?.supplier_id ? String(item.supplier_id) : '',
    min_level: String(item?.min_level ?? 0), target_level: item?.target_level != null ? String(item.target_level) : '',
    unit_cost: item?.unit_cost != null ? String(item.unit_cost) : '', storage_location: item?.storage_location ?? '',
    is_tracked_asset: item?.is_tracked_asset ?? false, opening_qty: '0', opening_location_id: String(me?.locations[0]?.id ?? ''),
  })
  const set = (key: keyof typeof form, value: string | boolean) => setForm((f) => ({ ...f, [key]: value }))

  // As the name is typed, show existing items with a similar name so a duplicate is noticed before saving.
  useEffect(() => {
    const text = form.name.trim()
    if (text.length < 3) return
    let live = true
    const timer = setTimeout(() => {
      api<Similar[]>(`/inventory/items/lookup${qs({ q: text })}`)
        .then((rows) => live && setSimilar(rows.filter((r) => r.id !== item?.id)))
        .catch(() => live && setSimilar([]))
    }, 250)
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [form.name, item?.id])

  const shownSimilar = form.name.trim().length >= 3 ? similar : []

  async function submit(event: FormEvent) {
    event.preventDefault()
    const common = {
      name: form.name, category_id: Number(form.category_id), unit_id: Number(form.unit_id),
      supplier_id: form.supplier_id ? Number(form.supplier_id) : null, min_level: Number(form.min_level),
      target_level: form.target_level === '' ? null : Number(form.target_level),
      unit_cost: form.unit_cost === '' ? null : Number(form.unit_cost), storage_location: form.storage_location || null,
    }
    const ok = await run(() => editing
      ? api(`/inventory/items/${item.id}`, { method: 'PUT', body: common })
      : api('/inventory/items', { body: { ...common, is_tracked_asset: form.is_tracked_asset,
        opening_qty: Number(form.opening_qty), opening_location_id: Number(form.opening_qty) > 0 ? Number(form.opening_location_id) : null } }),
    editing ? 'Item updated' : 'Item created')
    if (ok) onSaved()
  }

  return (
    <Modal open={open} title={editing ? 'Edit item' : 'Add item to the item master'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Name" hint={editing ? `Item ID ${item.code}` : 'The item ID is generated automatically.'}>
          <Input required value={form.name} onChange={(e) => set('name', e.target.value)} />
        </Field>
        {shownSimilar.length > 0 && (
          <div role="status" className="rounded-md border border-warn/50 bg-warn-soft px-3 py-2 text-sm text-warn">
            <p className="flex items-center gap-1 font-medium"><AlertTriangle className="h-4 w-4" aria-hidden /> Similar items already exist</p>
            <ul className="mt-1 list-inside list-disc">{shownSimilar.map((s) => <li key={s.id}>{s.code} - {s.name}{!s.active && ' (inactive)'}</li>)}</ul>
            <p className="mt-1">Use the existing item instead of adding a duplicate.</p>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Select required value={form.category_id} onChange={(e) => set('category_id', e.target.value)}>
              <option value="">Select</option>
              {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label="Unit of measure">
            <Select required value={form.unit_id} onChange={(e) => set('unit_id', e.target.value)}>
              <option value="">Select</option>
              {units.data?.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </Select>
          </Field>
          <Field label="Supplier">
            <Select value={form.supplier_id} onChange={(e) => set('supplier_id', e.target.value)}>
              <option value="">None</option>
              {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Unit cost"><Input type="number" step="0.01" min={0} value={form.unit_cost} onChange={(e) => set('unit_cost', e.target.value)} /></Field>
          <Field label="Minimum level"><Input type="number" min={0} value={form.min_level} onChange={(e) => set('min_level', e.target.value)} /></Field>
          <Field label="Target level"><Input type="number" min={0} value={form.target_level} onChange={(e) => set('target_level', e.target.value)} /></Field>
        </div>
        <Field label="Storage location"><Input value={form.storage_location} onChange={(e) => set('storage_location', e.target.value)} /></Field>
        {!editing && (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_tracked_asset} onChange={(e) => set('is_tracked_asset', e.target.checked)} /> Track individual assets</label>
        )}
        {!editing && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Opening stock" hint="Better: receive stock against an invoice."><Input type="number" min={0} value={form.opening_qty} onChange={(e) => set('opening_qty', e.target.value)} /></Field>
            <Field label="Opening location">
              <Select value={form.opening_location_id} onChange={(e) => set('opening_location_id', e.target.value)}>
                {me?.locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </Select>
            </Field>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Modal>
  )
}
