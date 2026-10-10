import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import type { Item } from '@/lib/useItems'
import { qs, useApi } from '@/lib/useApi'

interface ItemFormProps {
  kind: 'crockery' | 'smallware'
  item: Item | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}

export function ItemForm({ kind, item, open, onClose, onSaved }: ItemFormProps) {
  const { me } = useAuth()
  const run = useRun()
  const editing = item !== null
  const categories = useApi<{ id: number; name: string }[]>(`/inventory/categories${qs({ kind })}`)
  const units = useApi<{ id: number; name: string }[]>('/inventory/units')
  const [form, setForm] = useState({
    code: item?.code ?? '', name: item?.name ?? '', category_id: item ? String(item.category_id) : '',
    unit_id: item ? String(item.unit_id) : '', min_level: String(item?.min_level ?? 0),
    target_level: item?.target_level != null ? String(item.target_level) : '', unit_cost: item?.unit_cost != null ? String(item.unit_cost) : '',
    supplier: item?.supplier ?? '', storage_location: item?.storage_location ?? '', is_tracked_asset: item?.is_tracked_asset ?? false,
    opening_qty: '0', opening_location_id: String(me?.locations[0]?.id ?? ''),
  })
  const set = (key: keyof typeof form, value: string | boolean) => setForm((f) => ({ ...f, [key]: value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    const common = {
      name: form.name, category_id: Number(form.category_id), unit_id: Number(form.unit_id), min_level: Number(form.min_level),
      target_level: form.target_level === '' ? null : Number(form.target_level), unit_cost: form.unit_cost === '' ? null : Number(form.unit_cost),
      supplier: form.supplier || null, storage_location: form.storage_location || null,
    }
    const ok = await run(() => editing
      ? api(`/inventory/items/${item.id}`, { method: 'PUT', body: common })
      : api('/inventory/items', { body: { ...common, kind, code: form.code, is_tracked_asset: form.is_tracked_asset,
        opening_qty: Number(form.opening_qty), opening_location_id: Number(form.opening_qty) > 0 ? Number(form.opening_location_id) : null } }),
    editing ? 'Item updated' : 'Item created')
    if (ok) onSaved()
  }

  return (
    <Modal open={open} title={editing ? 'Edit item' : 'Add item'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {!editing && <Field label="Item code"><Input required value={form.code} onChange={(e) => set('code', e.target.value)} /></Field>}
          <Field label="Name"><Input required value={form.name} onChange={(e) => set('name', e.target.value)} /></Field>
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
          <Field label="Minimum level"><Input type="number" min={0} value={form.min_level} onChange={(e) => set('min_level', e.target.value)} /></Field>
          <Field label="Target level"><Input type="number" min={0} value={form.target_level} onChange={(e) => set('target_level', e.target.value)} /></Field>
          <Field label="Unit cost"><Input type="number" step="0.01" min={0} value={form.unit_cost} onChange={(e) => set('unit_cost', e.target.value)} /></Field>
          <Field label="Supplier"><Input value={form.supplier} onChange={(e) => set('supplier', e.target.value)} /></Field>
        </div>
        <Field label="Storage location"><Input value={form.storage_location} onChange={(e) => set('storage_location', e.target.value)} /></Field>
        {!editing && kind === 'smallware' && (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_tracked_asset} onChange={(e) => set('is_tracked_asset', e.target.checked)} /> Track individual assets</label>
        )}
        {!editing && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Opening stock"><Input type="number" min={0} value={form.opening_qty} onChange={(e) => set('opening_qty', e.target.value)} /></Field>
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
