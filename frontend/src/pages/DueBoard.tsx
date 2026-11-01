import { Check } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { fmtTime, label } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface Due {
  equipment_id: number
  equipment: string
  schedule_id: number
  stage: string
  slot_at: string
  opens_at: string
  open: boolean
  status: 'done' | 'due' | 'overdue' | 'upcoming'
}

export interface DueCard {
  first: Due
  stages: string[]
  status: Due['status']
  closed: boolean
}

const TONE = { done: 'ok', due: 'warn', overdue: 'critical', upcoming: 'neutral' } as const
const natural = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })

interface Props {
  cards: [string, DueCard][]
  kindOf: Map<number, string>
  timezone?: string
  canRecord: boolean
  onStart: (equipmentId: number, scheduleId: number) => void
}

/**
 * Today's checks, laid out as one row per monitoring point with its times as chips in time order, under a heading for the kind of point,
 * so a chiller checked at 09:00 and at 18:00 is one row, not two cards scattered among the others.
 */
export function DueBoard({ cards, kindOf, timezone, canRecord, onStart }: Props) {
  const [onlyOpen, setOnlyOpen] = useState(false)
  const points = new Map<number, { id: number; name: string; kind: string; cards: DueCard[] }>()
  for (const [, card] of cards) {
    const id = card.first.equipment_id
    const point = points.get(id) ?? { id, name: card.first.equipment, kind: kindOf.get(id) ?? 'Other', cards: [] }
    point.cards.push(card)
    points.set(id, point)
  }
  const rows = [...points.values()].map((p) => ({ ...p, cards: p.cards.sort((a, b) => a.first.slot_at.localeCompare(b.first.slot_at)) }))
  const shown = onlyOpen ? rows.filter((p) => p.cards.some((c) => c.status !== 'done')) : rows
  const kinds = [...new Set(shown.map((p) => p.kind))].sort(natural)
  const total = cards.length
  const done = cards.filter(([, c]) => c.status === 'done').length
  const late = cards.filter(([, c]) => c.status === 'overdue').length

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-ink-muted"><span className="font-semibold text-ink">{done} of {total}</span> recorded{late > 0 && <span className="font-semibold text-danger"> - {late} overdue</span>}</p>
        <label className="flex items-center gap-2"><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> Only what still needs doing</label>
      </div>
      {kinds.map((kind) => {
        const inKind = shown.filter((p) => p.kind === kind).sort((a, b) => natural(a.name, b.name))
        const slots = inKind.flatMap((p) => p.cards)
        return (
          <section key={kind} aria-label={kind}>
            <h3 className="mb-2 flex items-baseline gap-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
              {label(kind)}<span className="text-xs font-normal normal-case tracking-normal">{slots.filter((c) => c.status === 'done').length} of {slots.length} recorded</span>
            </h3>
            <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
              {inKind.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                  <span className="min-w-40 font-medium sm:w-56">{p.name}</span>
                  <span className="flex flex-wrap gap-2">
                    {p.cards.filter((c) => !onlyOpen || c.status !== 'done').map((c) => {
                      const finished = c.status === 'done'
                      return (
                        <button key={`${c.first.schedule_id}-${c.first.slot_at}`} type="button" disabled={!canRecord || c.closed || finished}
                          aria-label={`${p.name}, ${c.stages.map(label).join(' and ')} at ${fmtTime(c.first.slot_at, timezone)}, ${finished ? 'recorded' : c.closed ? 'not open yet' : label(c.status)}`}
                          onClick={() => onStart(c.first.equipment_id, c.first.schedule_id)}
                          className={cn('flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left text-sm',
                            finished ? 'border-ok/30 bg-ok-soft/50 text-ink-muted' : c.status === 'overdue' ? 'border-danger/40 bg-danger-soft/40' : c.status === 'due' ? 'border-warn/40 bg-warn-soft/40' : 'border-border',
                            canRecord && !c.closed && !finished && 'hover:bg-surface-muted')}>
                          <span className="font-semibold tabular-nums">{fmtTime(c.first.slot_at, timezone)}</span>
                          <span className="text-xs text-ink-muted">{c.stages.map(label).join(' and ')}</span>
                          {finished ? <Check className="h-4 w-4 text-ok" aria-hidden /> : <Badge tone={TONE[c.status]}>{c.closed ? `Opens ${fmtTime(c.first.opens_at, timezone)}` : label(c.status)}</Badge>}
                        </button>
                      )
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
      {kinds.length === 0 && <p className="py-6 text-center text-sm text-ink-muted">Everything for today is recorded.</p>}
    </div>
  )
}
