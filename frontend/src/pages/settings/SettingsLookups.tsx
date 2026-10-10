import { ManagedList } from '@/components/ManagedList'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import type { LookupKind } from '@/lib/useLookups'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Row {
  id: number
  value: string
  active: boolean
}

const LISTS: { kind: LookupKind; title: string; hint: string; placeholder: string }[] = [
  { kind: 'job_title', title: 'Job titles', hint: 'Suggested when adding or editing an employee.', placeholder: 'New job title' },
  { kind: 'checklist_category', title: 'Checklist categories', hint: 'Used when creating a checklist template.', placeholder: 'New category' },
  { kind: 'breakage_reason', title: 'Breakage reasons', hint: 'Choices when reporting breakage or damage.', placeholder: 'New reason' },
  { kind: 'corrective_action', title: 'Standard corrective actions', hint: 'Suggested after a failed check.', placeholder: 'New standard action' },
  { kind: 'monitoring_type', title: 'Monitoring types', hint: 'Groups monitoring points, such as cold storage, cooking or traceability.', placeholder: 'New monitoring type' },
]

function Lookup({ kind, title, hint, placeholder }: (typeof LISTS)[number]) {
  const run = useRun()
  const { data, reload } = useApi<Row[]>(`/lookups?kind=${kind}&include_inactive=true`)
  const act = async (call: () => Promise<unknown>, ok: string) => {
    const done = await run(call, ok)
    if (done) reload()
    return done
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <p className="text-sm text-ink-muted">{hint}</p>
      </CardHeader>
      <CardContent>
        <ManagedList
          entries={(data ?? []).map((r) => ({ id: r.id, name: r.value, active: r.active }))} placeholder={placeholder}
          onAdd={(value) => act(() => api('/lookups', { body: { kind, value } }), 'Added')}
          onRename={(id, value) => act(() => api(`/lookups/${id}`, { method: 'PUT', body: { value } }), 'Renamed')}
          onToggle={(id, active) => act(() => api(`/lookups/${id}`, { method: 'PUT', body: { active } }), active ? 'Restored' : 'Retired')}
        />
      </CardContent>
    </Card>
  )
}

export function SettingsLookups() {
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-muted">Dropdown choices used across the app. Retire a value to stop offering it; past records keep what they were saved with.</p>
      <div className="grid gap-4 lg:grid-cols-2">{LISTS.map((l) => <Lookup key={l.kind} {...l} />)}</div>
    </div>
  )
}
