import { CheckCircle2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { fmtDateTime, fmtLate, fmtTime } from '@/lib/format'

export interface WorkItem {
  kind: 'task' | 'check' | 'calibration'
  key: string
  title: string
  location_id: number
  location: string
  due_at: string | null
  state: 'overdue' | 'due_now' | 'due_soon'
  late_minutes: number | null
  equipment_id?: number
  note?: string | null
}

export interface MyWork {
  items: WorkItem[]
  next: { title: string; due_at: string; location_id: number } | null
}

const CHIP = { overdue: { tone: 'critical', text: 'Overdue' }, due_now: { tone: 'warn', text: 'Due now' }, due_soon: { tone: 'neutral', text: 'Due soon' } } as const
/** The time alone when it is today, with the date when it is not (a probe due last week). */
const when = (iso: string, zone?: string) => (new Date(iso).toDateString() === new Date().toDateString() ? fmtTime(iso, zone) : fmtDateTime(iso, zone))

const SHOWN = 8
const BUTTON = { task: 'Do it', check: 'Record', calibration: 'Check probe' } as const

/** Overdue first, then the earliest due; one with no time (a probe never checked) leads the overdue ones. */
const byUrgency = (a: WorkItem, b: WorkItem) =>
  Number(b.state === 'overdue') - Number(a.state === 'overdue') || (a.due_at ?? '').localeCompare(b.due_at ?? '')

/** Where the button goes; a check opens the recording form for that point, as scanning its code does. */
function targetOf(item: WorkItem): { to: string; state?: { locationId: number; equipmentId?: number } } {
  if (item.kind === 'calibration') return { to: '/calibration' }
  if (item.kind === 'check') return { to: '/monitoring', state: { locationId: item.location_id, equipmentId: item.equipment_id } }
  return { to: '/checklists', state: { locationId: item.location_id } }
}

/** What the steward should do now: one list in time order, each row with one big button that goes straight to doing it. */
export function MyWorkList({ work, timezoneOf, showPlace }: { work: MyWork; timezoneOf: (locationId: number) => string | undefined; showPlace: boolean }) {
  const [all, setAll] = useState(false)
  const sorted = [...work.items].sort(byUrgency)
  const items = all ? sorted : sorted.slice(0, SHOWN)  // a busy day is a long list: the most urgent come first, the rest one tap away
  if (items.length === 0) {
    return (
      <section aria-label="What to do now" className="flex flex-col items-center gap-2 rounded-2xl border border-border bg-surface px-4 py-8 text-center">
        <CheckCircle2 className="h-10 w-10 text-ok" aria-hidden />
        <p className="text-lg font-semibold">Nothing due right now</p>
        {work.next && <p className="text-sm text-ink-muted">Next: {work.next.title} at {fmtTime(work.next.due_at, timezoneOf(work.next.location_id))}</p>}
      </section>
    )
  }
  return (
    <section aria-label="What to do now" className="space-y-3">
      <h2 className="text-lg font-semibold">What to do now</h2>
      <ul className="space-y-3">
        {items.map((item) => {
          const chip = CHIP[item.state]
          const { to, state } = targetOf(item)
          return (
            <li key={item.key} className={`rounded-2xl border bg-surface p-4 ${item.state === 'overdue' ? 'border-danger/50' : 'border-border'}`}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={chip.tone}>{chip.text}</Badge>
                {!!item.late_minutes && <Badge tone="warn">Late by {fmtLate(item.late_minutes)}</Badge>}
              </div>
              <p className="mt-2 text-base font-semibold leading-snug">{item.title}</p>
              <p className="mt-0.5 text-sm text-ink-muted">
                {showPlace && <>{item.location} · </>}
                {item.due_at ? <>Due {when(item.due_at, timezoneOf(item.location_id))}</> : item.note}
              </p>
              <Link to={to} state={state} aria-label={`${BUTTON[item.kind]}: ${item.title}`}
                className="mt-3 flex min-h-12 w-full items-center justify-center rounded-xl bg-brand px-4 text-base font-semibold text-white active:opacity-90">
                {BUTTON[item.kind]}
              </Link>
            </li>
          )
        })}
      </ul>
      {sorted.length > SHOWN && (
        <button type="button" onClick={() => setAll((v) => !v)} className="flex min-h-12 w-full items-center justify-center rounded-xl border border-border bg-surface px-4 text-base font-medium">
          {all ? 'Show fewer' : `Show all ${sorted.length}`}
        </button>
      )}
    </section>
  )
}
