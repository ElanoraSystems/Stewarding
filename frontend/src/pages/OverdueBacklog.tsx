import { ChevronDown } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fmtDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Instance } from '@/pages/ChecklistTaskCard'

interface Props {
  items: Instance[]
  total: number
  canWaive: boolean
  /** Waive every overdue task of one day: asks for the reason, then waives them. */
  onWaiveDay: (ids: number[], day: string) => void
  renderDay: (day: string, tasks: Instance[]) => ReactNode
}

const weekday = (day: string) => new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' }).format(new Date(`${day}T00:00:00Z`))

/** Every overdue task in one place, newest day first, so nobody has to step through the dates one by one. */
export function OverdueBacklog({ items, total, canWaive, onWaiveDay, renderDay }: Props) {
  const days = [...new Set(items.map((i) => i.local_date))].sort().reverse()
  const [open, setOpen] = useState<Set<string>>(new Set())
  const toggle = (day: string) => setOpen((o) => { const next = new Set(o); if (!next.delete(day)) next.add(day); return next })
  const checklists = new Set(items.map((i) => i.template_name)).size
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-ink-muted"><span className="font-semibold text-danger">{total} overdue task{total === 1 ? '' : 's'}</span> over {days.length} day{days.length === 1 ? '' : 's'} and {checklists} checklist{checklists === 1 ? '' : 's'}{total > items.length && ` - showing the newest ${items.length}`}</p>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen(new Set(days))}>Open all days</Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(new Set())}>Close all days</Button>
        </div>
      </div>
      {days.map((day) => (
        <Day key={day} day={day} tasks={items.filter((i) => i.local_date === day)} open={open.has(day)} onToggle={() => toggle(day)} canWaive={canWaive} onWaive={onWaiveDay}>
          {renderDay(day, items.filter((i) => i.local_date === day))}
        </Day>
      ))}
    </div>
  )
}

function Day({ day, tasks, open, onToggle, canWaive, onWaive, children }: { day: string; tasks: Instance[]; open: boolean; onToggle: () => void; canWaive: boolean; onWaive: Props['onWaiveDay']; children: ReactNode }) {
  const body = useId()
  const lists = new Set(tasks.map((t) => t.template_name)).size
  return (
    <section aria-label={fmtDate(day)} className="overflow-hidden rounded-2xl border border-danger/30 bg-surface">
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <button type="button" aria-expanded={open} aria-controls={body} onClick={onToggle} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className="text-lg font-semibold">{weekday(day)}, {fmtDate(day)}</span>
          <Badge tone="critical">{tasks.length} overdue</Badge>
          <span className="hidden text-sm text-ink-muted sm:inline">{lists} checklist{lists === 1 ? '' : 's'}</span>
          <ChevronDown aria-hidden className={cn('ci-chevron ml-auto h-5 w-5 shrink-0 text-ink-muted', open && 'rotate-180')} />
        </button>
        {canWaive && <Button size="sm" variant="outline" onClick={() => onWaive(tasks.map((t) => t.id), day)}>Waive all {tasks.length}</Button>}
      </div>
      <div id={body} className="ci-collapse" data-open={open} aria-hidden={!open} {...(open ? {} : { inert: true })}>
        <div className="overflow-hidden"><div className="border-t border-border bg-surface-muted/30 p-4">{children}</div></div>
      </div>
    </section>
  )
}
