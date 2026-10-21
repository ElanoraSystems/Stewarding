import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Skeleton, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'
import type { Rules } from '@/pages/trace/types'

/** How long each kind of food keeps in each condition, in hours; the use-by date of a lot is worked out from these. */
export function RulesTab() {
  const { me } = useAuth()
  const run = useRun()
  const { data, reload } = useApi<Rules>('/lots/rules')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const canEdit = me?.permissions.includes('lot.manage') ?? false

  if (!data) return <Skeleton className="h-48 w-full" />
  const current = (group: string, condition: string) => data.rules.find((r) => r.food_group === group && r.condition === condition)
  const key = (group: string, condition: string) => `${group}:${condition}`

  async function save(group: string, condition: string) {
    const typed = draft[key(group, condition)]
    const existing = current(group, condition)
    setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== key(group, condition))))
    if (typed === undefined || typed === String(existing?.hours ?? '')) return
    const ok = typed === ''
      ? existing && await run(() => api(`/lots/rules/${existing.id}`, { method: 'DELETE' }), 'Rule removed')
      : await run(() => api('/lots/rules', { method: 'PUT', body: { food_group: group, condition, hours: Number(typed) } }), 'Rule saved')
    if (ok) reload()
  }

  return (
    <div className="space-y-3">
      <p className="max-w-3xl text-sm text-ink-muted">
        Set how many hours each kind of food keeps once it is in that condition, to match your local food-safety rules (72 hours is 3 days, 120 hours is 5 days).
        A portion lot gets a use-by date that many hours after the split, never later than its parent&apos;s. A food and condition with no rule cannot be split until a manager sets one.
        {!canEdit && ' Only a manager can change these.'}
      </p>
      <Table>
        <thead><tr><Th>Food</Th>{data.conditions.map((c) => <Th key={c.key} className="text-right">{c.label} (hours)</Th>)}</tr></thead>
        <tbody>
          {data.groups.map((g) => (
            <tr key={g.key}>
              <Td className="font-medium">{g.label}</Td>
              {data.conditions.map((c) => (
                <Td key={c.key} className="text-right">
                  <Input
                    aria-label={`${g.label}, ${c.label}, hours`}
                    type="number"
                    min={1}
                    max={8760}
                    disabled={!canEdit}
                    className="ml-auto h-9 w-24 text-right tabular-nums"
                    placeholder="not set"
                    value={draft[key(g.key, c.key)] ?? String(current(g.key, c.key)?.hours ?? '')}
                    onChange={(e) => setDraft((d) => ({ ...d, [key(g.key, c.key)]: e.target.value }))}
                    onBlur={() => save(g.key, c.key)}
                    onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
                  />
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
