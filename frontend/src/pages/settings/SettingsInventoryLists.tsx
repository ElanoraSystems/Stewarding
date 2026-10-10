import { ManagedList } from '@/components/ManagedList'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

interface Row {
  id: number
  name: string
  active: boolean
}

function CategoryList({ kind, title }: { kind: 'crockery' | 'smallware'; title: string }) {
  const run = useRun()
  const { data, reload } = useApi<Row[]>(`/inventory/categories${qs({ kind, include_inactive: true })}`)
  const act = async (call: () => Promise<unknown>, ok: string) => {
    const done = await run(call, ok)
    if (done) reload()
    return done
  }
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        <ManagedList
          entries={data ?? []} placeholder="New category"
          onAdd={(name) => act(() => api('/inventory/categories', { body: { kind, name } }), 'Category added')}
          onRename={(id, name) => act(() => api(`/inventory/categories/${id}`, { method: 'PUT', body: { name } }), 'Category renamed')}
          onToggle={(id, active) => act(() => api(`/inventory/categories/${id}`, { method: 'PUT', body: { active } }), active ? 'Category restored' : 'Category retired')}
        />
      </CardContent>
    </Card>
  )
}

function UnitList() {
  const run = useRun()
  const { data, reload } = useApi<Row[]>('/inventory/units?include_inactive=true')
  const act = async (call: () => Promise<unknown>, ok: string) => {
    const done = await run(call, ok)
    if (done) reload()
    return done
  }
  return (
    <Card>
      <CardHeader><CardTitle>Units of measure</CardTitle></CardHeader>
      <CardContent>
        <ManagedList
          entries={data ?? []} placeholder="New unit, e.g. Box"
          onAdd={(name) => act(() => api('/inventory/units', { body: { name } }), 'Unit added')}
          onRename={(id, name) => act(() => api(`/inventory/units/${id}`, { method: 'PUT', body: { name } }), 'Unit renamed')}
          onToggle={(id, active) => act(() => api(`/inventory/units/${id}`, { method: 'PUT', body: { active } }), active ? 'Unit restored' : 'Unit retired')}
        />
      </CardContent>
    </Card>
  )
}

export function SettingsInventoryLists() {
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-muted">Categories and units appear in the item master. Retired values stay on existing items but cannot be chosen for new ones.</p>
      <div className="grid gap-4 lg:grid-cols-3">
        <CategoryList kind="crockery" title="Crockery categories" />
        <CategoryList kind="smallware" title="Smallware categories" />
        <UnitList />
      </div>
    </div>
  )
}
