import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fmtDateTime } from '@/lib/format'
import { groupNotes, KIND_TITLE, needsAcknowledging, needsDecision, type Note } from '@/lib/notes'
import { cn } from '@/lib/utils'

interface Props {
  items: Note[]
  places: Map<number, string>
  canDecide: boolean
  selected: number[]
  onToggle: (id: number) => void
  onRead: (id: number) => void
  onAcknowledge: (ids: number[]) => void
  onDecide: (ids: number[], initial: 'approved' | 'rejected') => void
}

export function NotificationList(p: Props) {
  return (
    <ul className="space-y-2">
      {groupNotes(p.items).map((g) => (g.length === 1 ? <li key={g[0].id}><Card n={g[0]} {...p} /></li> : <li key={g[0].id}><Group group={g} {...p} /></li>))}
    </ul>
  )
}

function Buttons({ n, canDecide, onRead, onAcknowledge, onDecide }: { n: Note } & Props) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {n.link && <Button asChild size="sm" variant="outline"><Link to={n.link}>Open</Link></Button>}
      {!n.read_at && !needsAcknowledging(n) && <Button size="sm" variant="ghost" onClick={() => onRead(n.id)}>Mark read</Button>}
      {canDecide && needsAcknowledging(n) && <Button size="sm" onClick={() => onAcknowledge([n.id])}>Acknowledge</Button>}
      {canDecide && needsDecision(n) && <>
        <Button size="sm" onClick={() => onDecide([n.id], 'approved')}>Approve</Button>
        <Button size="sm" variant="outline" className="text-danger" onClick={() => onDecide([n.id], 'rejected')}>Reject</Button>
      </>}
    </div>
  )
}

function Card({ n, ...p }: { n: Note } & Props) {
  return (
    <div className={cn('rounded-lg border bg-surface p-4 text-sm', n.action_needed ? 'border-danger/60 bg-danger-soft' : n.priority === 'high' ? 'border-warn/50' : 'border-border')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className={cn('flex items-center gap-2', !n.read_at && 'font-semibold')}>
          {p.canDecide && needsDecision(n) && <input type="checkbox" aria-label={`Select ${n.title}`} checked={p.selected.includes(n.id)} onChange={() => p.onToggle(n.id)} />}
          {n.title}
        </p>
        <div className="flex items-center gap-1">
          {n.priority !== 'normal' && <Badge tone={n.priority === 'critical' ? 'critical' : 'warn'}>{n.priority}</Badge>}
          {n.action_needed && <Badge tone="critical">Action needed</Badge>}
        </div>
      </div>
      {n.body && <p className="mt-1 text-ink-muted">{n.body}</p>}
      <p className="mt-1 text-xs text-ink-muted">{fmtDateTime(n.created_at)}{n.location_id && ` - ${p.places.get(n.location_id) ?? ''}`}</p>
      <Buttons n={n} {...p} />
    </div>
  )
}

function Group({ group, ...p }: { group: Note[] } & Props) {
  const [open, setOpen] = useState(false)
  const first = group[0]
  const waiting = group.filter(needsAcknowledging)
  const critical = group.some((n) => n.priority === 'critical')
  return (
    <div className={cn('rounded-lg border bg-surface text-sm', first.action_needed ? 'border-danger/60 bg-danger-soft' : 'border-border')}>
      <div className="flex flex-wrap items-center justify-between gap-2 p-4">
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 basis-56 items-center gap-2 text-left">
          <ChevronRight className={cn('size-4 shrink-0 text-ink-muted transition-transform', open && 'rotate-90')} aria-hidden />
          <span className="min-w-0">
            <span className={cn('block', group.some((n) => !n.read_at) && 'font-semibold')}>{KIND_TITLE[first.kind] ?? 'Alerts'}</span>
            <span className="block text-xs text-ink-muted">{first.location_id ? `${p.places.get(first.location_id) ?? ''} · ` : ''}{new Date(first.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} · {group.length} alerts</span>
          </span>
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {critical && <Badge tone="critical">critical</Badge>}
          {p.canDecide && waiting.length > 0 && <Button size="sm" onClick={() => p.onAcknowledge(waiting.map((n) => n.id))}>Acknowledge all ({waiting.length})</Button>}
        </div>
      </div>
      {open && (
        <ul className="divide-y divide-border border-t border-border">
          {group.map((n) => (
            <li key={n.id} className="px-4 py-3 pl-10">
              <p className={cn(!n.read_at && 'font-semibold')}>{n.title}</p>
              {n.body && <p className="mt-0.5 text-ink-muted">{n.body}</p>}
              <p className="mt-0.5 text-xs text-ink-muted">{fmtDateTime(n.created_at)}</p>
              <Buttons n={n} {...p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
