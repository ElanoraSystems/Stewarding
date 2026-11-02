import { ChevronDown } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fmtTime, label } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Instance } from '@/pages/ChecklistTaskCard'

const DONE = ['completed', 'pending_verification', 'verified', 'waived']

interface Group {
  name: string
  category: string
  frequency: string
  items: Instance[]
  open: Instance[]
  done: number
  overdue: number
  awaiting: number
  nextDue: string | null
}

/** One group per checklist: its tasks (open ones first, by time), how far along it is, and what is late. */
function groupChecklists(items: Instance[], places?: Map<number, string>): Group[] {
  const byName = new Map<string, Instance[]>()
  const several = places !== undefined && new Set(items.map((i) => i.location_id)).size > 1  // the same checklist at two places is two groups
  const nameOf = (i: Instance) => `${i.template_name ?? 'Checklist'}${several ? ` - ${places!.get(i.location_id) ?? ''}` : ''}`
  for (const i of items) byName.set(nameOf(i), [...(byName.get(nameOf(i)) ?? []), i])
  const groups = [...byName].map(([name, list]) => {
    const open = list.filter((i) => !DONE.includes(i.effective_status)).sort((a, b) => (a.due_at ?? '').localeCompare(b.due_at ?? ''))
    const finished = list.filter((i) => DONE.includes(i.effective_status)).sort((a, b) => (a.due_at ?? '').localeCompare(b.due_at ?? ''))
    return {
      name, category: list[0].category, frequency: list[0].frequency, items: [...open, ...finished], open,
      done: list.length - open.length,
      overdue: list.filter((i) => i.effective_status === 'overdue').length,
      awaiting: list.filter((i) => i.effective_status === 'pending_verification').length,
      nextDue: open.find((i) => i.due_at)?.due_at ?? null,
    }
  })
  // checklists with work left come first, earliest due first (so Opening comes before Closing); finished ones last
  return groups.sort((a, b) => Number(a.open.length === 0) - Number(b.open.length === 0) || (a.nextDue ?? '9').localeCompare(b.nextDue ?? '9') || a.name.localeCompare(b.name))
}

interface Props {
  items: Instance[]
  /** Location names, so checklists of the same name at different places stay apart. */
  places?: Map<number, string>
  timezone?: string
  /** Whether every checklist starts open, as when a filter is set and the person is looking for something. */
  openAll?: boolean
  renderTask: (task: Instance) => ReactNode
  /** In select mode: a way to tick every task of one checklist at once. */
  selection?: { selectable: Set<number>; selected: number[]; onSet: (ids: number[], on: boolean) => void }
}

/**
 * The tasks of a day as separate checklists, each a section that opens and closes, with its own progress and what is late.
 * Every checklist starts closed, showing only its progress and what is late, so a long checklist never pushes the others off the screen.
 */
export function ChecklistGroups({ items, places, timezone, openAll = false, renderTask, selection }: Props) {
  const groups = groupChecklists(items, places)
  const [choice, setChoice] = useState<Record<string, boolean>>({})
  const isOpen = (g: Group) => choice[g.name] ?? openAll
  const setAll = (value: boolean) => setChoice(Object.fromEntries(groups.map((g) => [g.name, value])))

  return (
    <div className="space-y-3">
      {groups.length > 1 && (
        <div className="flex items-center justify-between gap-3 text-sm">
          <p className="text-ink-muted">{groups.length} checklists</p>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setAll(true)}>Open all</Button>
            <Button size="sm" variant="ghost" onClick={() => setAll(false)}>Close all</Button>
          </div>
        </div>
      )}
      {groups.map((g) => (
        <Section key={g.name} group={g} open={isOpen(g)} onToggle={() => setChoice((c) => ({ ...c, [g.name]: !isOpen(g) }))} timezone={timezone} selection={selection}>
          <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">{g.items.map((task) => <div key={task.id}>{renderTask(task)}</div>)}</div>
        </Section>
      ))}
    </div>
  )
}

function Section({ group: g, open, onToggle, timezone, selection, children }: { group: Group; open: boolean; onToggle: () => void; timezone?: string; selection?: Props['selection']; children: ReactNode }) {
  const body = useId()
  const percent = g.items.length ? Math.round((g.done / g.items.length) * 100) : 0
  const allDone = g.open.length === 0
  const ticks = selection ? g.items.filter((i) => selection.selectable.has(i.id)).map((i) => i.id) : []
  const everyTicked = ticks.length > 0 && ticks.every((id) => selection?.selected.includes(id))
  return (
    <section aria-label={g.name} className={cn('overflow-hidden rounded-2xl border bg-surface', g.overdue > 0 ? 'border-danger/40' : 'border-border')}>
      <button type="button" aria-expanded={open} aria-controls={body} onClick={onToggle}
        className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-surface-muted/60">
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-lg font-semibold">{g.name}</span>
            <Badge>{label(g.category)}</Badge>
            <Badge>{label(g.frequency)}</Badge>
          </span>
          <span className="mt-2 flex items-center gap-3">
            <span className="h-2 max-w-xs flex-1 overflow-hidden rounded bg-border" role="img" aria-label={`${percent}% done`}>
              <span className={cn('block h-full rounded transition-[width] duration-500', allDone ? 'bg-ok' : g.overdue > 0 ? 'bg-danger' : 'bg-brand')} style={{ width: `${percent}%` }} />
            </span>
            <span className="text-sm tabular-nums text-ink-muted">{g.done} of {g.items.length} done</span>
          </span>
        </span>
        <span className="hidden shrink-0 flex-wrap items-center justify-end gap-2 sm:flex">
          {g.overdue > 0 && <Badge tone="critical">{g.overdue} overdue</Badge>}
          {g.awaiting > 0 && <Badge tone="warn">{g.awaiting} awaiting approval</Badge>}
          {allDone ? <Badge tone="ok">All done</Badge> : g.nextDue && <span className="text-sm text-ink-muted">Next due {fmtTime(g.nextDue, timezone)}</span>}
        </span>
        <ChevronDown aria-hidden className={cn('ci-chevron h-5 w-5 shrink-0 text-ink-muted', open && 'rotate-180')} />
      </button>
      <div id={body} className="ci-collapse" data-open={open} aria-hidden={!open} {...(open ? {} : { inert: true })}>
        <div className="overflow-hidden">
          <div className="space-y-3 border-t border-border bg-surface-muted/30 p-4">
            {selection && ticks.length > 0 && (
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" checked={everyTicked} onChange={(e) => selection.onSet(ticks, e.target.checked)} /> Select all in {g.name} ({ticks.length})
              </label>
            )}
            {children}
          </div>
        </div>
      </div>
    </section>
  )
}
