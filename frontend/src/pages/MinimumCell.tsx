import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import type { Item } from '@/lib/useItems'

interface Props {
  item: Item
  locationId: number | null
  canEdit: boolean
  onSaved: () => void
}

/** The minimum for one location when a location is chosen, otherwise the item's own minimum with the places that fall short. */
export function MinimumCell({ item, locationId, canEdit, onSaved }: Props) {
  const { me } = useAuth()
  const run = useRun()
  const custom = locationId !== null && item.location_minimums[locationId] !== undefined
  const [draft, setDraft] = useState<string | null>(null)
  const names = new Map(me?.locations.map((l) => [l.id, l.name]))

  async function save() {
    const typed = draft
    setDraft(null)
    if (typed === null || typed === String(item.minimum)) return
    const body = { min_level: typed === '' ? null : Number(typed) }
    if (await run(() => api(`/inventory/items/${item.id}/levels/${locationId}`, { method: 'PUT', body }), 'Minimum updated')) onSaved()
  }

  if (locationId === null) {
    return (
      <div className="text-right">
        <span className="tabular-nums">{item.min_level}</span>
        {item.short_at.map((s) => (
          <p key={s.location_id} className="text-xs text-danger">{names.get(s.location_id) ?? 'Location'}: {s.qty} of {s.minimum}</p>
        ))}
      </div>
    )
  }
  return (
    <div className="flex flex-col items-end">
      {canEdit ? (
        <Input
          aria-label={`Minimum for ${item.name}`}
          type="number"
          min={0}
          className="h-8 w-20 text-right tabular-nums"
          value={draft ?? String(item.minimum)}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
        />
      ) : <span className="tabular-nums">{item.minimum}</span>}
      <span className="text-[11px] text-ink-muted">{custom ? 'set for this location' : 'item default'}</span>
    </div>
  )
}
