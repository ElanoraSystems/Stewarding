import { Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { Item } from '@/lib/useItems'
import { ItemForm } from '@/pages/ItemForm'

const SIZE = 15

export function SettingsItems() {
  const run = useRun()
  const [categoryId, setCategoryId] = useState('')
  const [search, setSearch] = useState('')
  const [active, setActive] = useState('true')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Item | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const categories = useApi<{ id: number; name: string }[]>('/inventory/categories')
  const { data, loading, reload } = useApi<{ total: number; items: Item[] }>(
    `/inventory/items${qs({ category_id: categoryId, search, active, page, size: SIZE })}`,
  )

  async function toggle(item: Item) {
    const ok = await run(() => api(`/inventory/items/${item.id}`, { method: 'PUT', body: { active: !item.active } }),
      item.active ? 'Item retired' : 'Item restored')
    if (ok) reload()
  }

  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1) }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-3">
        <Button onClick={() => { setEditing(null); setFormOpen(true) }}><Plus className="h-4 w-4" /> Add item</Button>
      </div>
      <div className="flex flex-wrap gap-3">
        <Select aria-label="Category" className="w-auto" value={categoryId} onChange={(e) => reset(setCategoryId)(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <div className="relative min-w-52 flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-muted" aria-hidden />
          <Input aria-label="Search items" className="pl-9" placeholder="Search name or code" value={search} onChange={(e) => reset(setSearch)(e.target.value)} />
        </div>
        <Select aria-label="Status" className="w-auto" value={active} onChange={(e) => reset(setActive)(e.target.value)}>
          <option value="true">Active items</option>
          <option value="false">Retired items</option>
        </Select>
      </div>
      <Table>
        <thead>
          <tr><Th>Item ID</Th><Th>Name</Th><Th>Category</Th><Th>Unit</Th><Th>Supplier</Th><Th className="text-right">Cost</Th><Th className="text-right">Min / target</Th><Th /></tr>
        </thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={8} /> : data?.items.map((i) => (
            <tr key={i.id}>
              <Td>{i.code}</Td>
              <Td className="font-medium">{i.name}{i.is_tracked_asset && <Badge className="ml-2">Asset</Badge>}</Td>
              <Td>{i.category}</Td>
              <Td>{i.unit}</Td>
              <Td>{i.supplier ?? '-'}</Td>
              <Td className="text-right tabular-nums">{i.unit_cost != null ? i.unit_cost.toFixed(2) : '-'}</Td>
              <Td className="text-right tabular-nums">{i.min_level} / {i.target_level ?? '-'}</Td>
              <Td className="space-x-2 text-right">
                <Button size="sm" variant="outline" onClick={() => { setEditing(i); setFormOpen(true) }}>Edit</Button>
                <Button size="sm" variant="outline" onClick={() => toggle(i)}>{i.active ? 'Retire' : 'Restore'}</Button>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.items.length === 0 && <EmptyState title="No items found" />}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}
      {formOpen && <ItemForm item={editing} open onClose={() => setFormOpen(false)} onSaved={() => { setFormOpen(false); reload() }} />}
    </div>
  )
}
