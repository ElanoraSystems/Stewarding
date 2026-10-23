import { Pencil, Plus, Power, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { CardGrid, RecordCard, SectionHeader } from '@/components/ui/record-card'
import { Select } from '@/components/ui/select'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { Item } from '@/lib/useItems'
import { ItemForm } from '@/pages/ItemForm'

const SIZE = 12

export function SettingsItems() {
  const run = useRun()
  const [categoryId, setCategoryId] = useState('')
  const [search, setSearch] = useState('')
  const [active, setActive] = useState('true')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Item | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [removing, setRemoving] = useState<Item | null>(null)
  const categories = useApi<{ id: number; name: string }[]>('/inventory/categories')
  const { data, reload } = useApi<{ total: number; items: Item[] }>(
    `/inventory/items${qs({ category_id: categoryId, search, active, page, size: SIZE })}`,
  )

  async function toggle(item: Item) {
    const ok = await run(() => api(`/inventory/items/${item.id}`, { method: 'PUT', body: { active: !item.active } }),
      item.active ? 'Item made inactive' : 'Item made active')
    if (ok) reload()
  }

  async function remove() {
    if (!removing) return
    const done = await run(() => api(`/inventory/items/${removing.id}`, { method: 'DELETE' }), 'Item deleted')
    setRemoving(null)
    if (done) reload()
  }

  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1) }

  return (
    <div className="space-y-6">
      <SectionHeader title="Item master" count={data?.total}
        action={<Button onClick={() => { setEditing(null); setFormOpen(true) }}><Plus className="h-4 w-4" /> Add item</Button>} />

      <div className="flex flex-wrap gap-3 rounded-xl border border-border bg-surface p-4">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-muted" aria-hidden />
          <Input aria-label="Search items" className="pl-9" placeholder="Search name or code" value={search} onChange={(e) => reset(setSearch)(e.target.value)} />
        </div>
        <Select aria-label="Category" className="w-auto" value={categoryId} onChange={(e) => reset(setCategoryId)(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select aria-label="Status" className="w-auto" value={active} onChange={(e) => reset(setActive)(e.target.value)}>
          <option value="true">Active items</option>
          <option value="false">Inactive items</option>
        </Select>
      </div>

      {!data ? <Skeleton className="h-48 w-full" /> : data.items.length === 0 ? <EmptyState title="No items found" /> : (
        <CardGrid>
          {data.items.map((i) => (
            <RecordCard
              key={i.id}
              title={i.name}
              subtitle={`${i.code} - ${i.category}`}
              inactive={!i.active}
              badges={<>{i.is_tracked_asset && <Badge>Asset</Badge>}<Badge tone={i.active ? 'ok' : 'neutral'}>{i.active ? 'Active' : 'Inactive'}</Badge></>}
              facts={[
                { label: 'Unit', value: i.unit },
                { label: 'Supplier', value: i.supplier ?? '-' },
                { label: 'Unit cost', value: i.unit_cost != null ? i.unit_cost.toFixed(2) : '-' },
                { label: 'Minimum / target', value: `${i.min_level} / ${i.target_level ?? '-'}` },
              ]}
              actions={[
                { label: 'Edit', icon: Pencil, onClick: () => { setEditing(i); setFormOpen(true) } },
                { label: i.active ? 'Make inactive' : 'Make active', icon: Power, onClick: () => toggle(i) },
                { label: 'Delete', icon: Trash2, tone: 'danger', onClick: () => setRemoving(i) },
              ]}
            />
          ))}
        </CardGrid>
      )}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}

      {formOpen && <ItemForm item={editing} open onClose={() => setFormOpen(false)} onSaved={() => { setFormOpen(false); reload() }} />}

      <ConfirmDialog open={removing !== null} title="Delete item" confirmLabel="Delete item"
        message={`Delete ${removing?.name ?? 'this item'}? This cannot be undone. An item with stock, receipts, counts or other history cannot be deleted; make it inactive instead.`}
        onConfirm={remove} onCancel={() => setRemoving(null)} />
    </div>
  )
}
