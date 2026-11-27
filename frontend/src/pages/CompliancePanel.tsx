import { CircleAlert, ClipboardCheck, Clock, Thermometer, TriangleAlert, Wrench } from 'lucide-react'
import { useState } from 'react'
import { KpiCard } from '@/components/KpiCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { qs, useApi } from '@/lib/useApi'

interface Timing { due: number; on_time: number; percent: number | null }
interface Checks { done: number; due: number; missed: number; failed: number; percent: number | null }
interface Outlet {
  location_id: number
  location: string
  checklists: Timing | null
  monitoring: Checks | null
  ccp: Checks | null
  failed_readings: number | null
  open_actions: number | null
  overdue_now: number | null
  probes: { total: number; needs_calibration: number; due_soon: number } | null
  missed_by_hour: { monitoring: number[]; tasks: number[] }
}
interface Compliance {
  range: { date_from: string; date_to: string }
  sections: string[]
  outlets: Outlet[]
}

const show = (percent: number | null) => (percent === null ? 'n/a' : `${percent}%`)
const toneOf = (percent: number | null) => (percent === null ? 'default' : percent >= 90 ? 'ok' : percent >= 70 ? 'warn' : 'critical')
const count = (n: number) => (n > 0 ? 'critical' : 'default')
const hourText = (h: number) => `${String(h).padStart(2, '0')}:00`

/** One row of 24 hour boxes: the number in each box says how many slipped in that hour, the shade only helps the eye. */
export function MissedByHour({ title, hours }: { title: string; hours: number[] }) {
  const top = Math.max(...hours)
  const total = hours.reduce((a, b) => a + b, 0)
  const worst = hours.map((n, h) => [n, h] as const).filter(([n]) => n > 0 && n === top).map(([, h]) => hourText(h))
  const summary = total === 0 ? 'none missed' : `${total} missed, most at ${worst.join(' and ')}`
  const shade = (n: number) => (n === 0 ? 'bg-surface-muted text-ink-muted' : n * 3 <= top ? 'bg-warn-soft text-warn' : n * 3 <= top * 2 ? 'bg-warn/30 text-ink' : 'bg-danger text-danger-ink')
  return (
    <div>
      <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm"><span className="font-medium">{title}</span><span className="text-xs text-ink-muted">{summary}</span></p>
      <ol className="mt-1 grid grid-cols-12 gap-0.5 sm:grid-cols-[repeat(24,minmax(0,1fr))]" aria-label={`${title} by hour of the day: ${summary}`}>
        {hours.map((n, h) => (
          <li key={h} title={`${hourText(h)}: ${n} missed`} className={cn('rounded-sm py-1 text-center text-[11px] tabular-nums leading-tight', shade(n))}>
            <span className="block">{n || '·'}</span>
            <span className="block text-[9px] opacity-80">{h}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** The strip of 24 hour boxes is only worth its space when something was missed; otherwise one line says so. */
function Missed({ title, hours }: { title: string; hours: number[] }) {
  if (hours.some((n) => n > 0)) return <MissedByHour title={title} hours={hours} />
  return <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm"><span className="font-medium">{title}</span><span className="text-xs text-ink-muted">none missed</span></p>
}

/** An outlet with nothing due in the period and nothing open has nothing to show, so it is listed on one line instead of a card. */
const idle = (o: Outlet) => (!o.checklists || o.checklists.due === 0) && (!o.monitoring || o.monitoring.due === 0) && !o.failed_readings && !o.open_actions && !o.overdue_now && !o.probes?.needs_calibration

/** The worst outlet first: lowest on-time percentage, then most failed readings. */
const worst = (o: Outlet) => Math.min(...[o.checklists?.percent, o.monitoring?.percent, o.ccp?.due ? o.ccp.percent : null].map((p) => p ?? 101))

function OutletCard({ o }: { o: Outlet }) {
  const c = o.checklists
  const m = o.monitoring
  const k = o.ccp
  return (
    <Card>
      <CardHeader><CardTitle>{o.location}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {c && <KpiCard icon={ClipboardCheck} label={`Tasks on time (${c.on_time} of ${c.due})`} value={show(c.percent)} tone={toneOf(c.percent)} />}
          {m && <KpiCard icon={Thermometer} label={`Checks recorded on time (${m.done} of ${m.due})`} value={show(m.percent)} tone={toneOf(m.percent)} />}
          {k && k.due > 0 && <KpiCard icon={Thermometer} label={`Critical (CCP) checks on time (${k.done} of ${k.due})`} value={show(k.percent)} tone={toneOf(k.percent)} />}
          {o.failed_readings !== null && <KpiCard icon={TriangleAlert} label={k && k.failed > 0 ? `Failed readings (${k.failed} critical)` : 'Failed readings'} value={o.failed_readings} tone={count(o.failed_readings)} />}
          {o.open_actions !== null && <KpiCard icon={CircleAlert} label="Open corrective actions" value={o.open_actions} tone={o.open_actions ? 'warn' : 'default'} />}
          {o.overdue_now !== null && <KpiCard icon={Clock} label="Overdue now" value={o.overdue_now} tone={count(o.overdue_now)} />}
          {o.probes && o.probes.total > 0 && (
            <KpiCard icon={Wrench} label={`Probes needing calibration${o.probes.due_soon ? ` (${o.probes.due_soon} more due soon)` : ''}`} value={o.probes.needs_calibration} tone={o.probes.needs_calibration ? 'critical' : 'default'} />
          )}
        </div>
        {m && <Missed title="Monitoring checks missed, by hour they were due" hours={o.missed_by_hour.monitoring} />}
        {c && <Missed title="Tasks not done on time, by hour they were due" hours={o.missed_by_hour.tasks} />}
      </CardContent>
    </Card>
  )
}

/** How each outlet is keeping up over the last few days; managers see every outlet, supervisors their own. */
export function CompliancePanel({ locationId }: { locationId: number | null }) {
  const [days, setDays] = useState('7')
  const { data, loading, error } = useApi<Compliance>(`/dashboard/compliance${qs({ days, location_id: locationId })}`)
  return (
    <section aria-label="Compliance by outlet" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">How each outlet is doing</h2>
        <Select aria-label="Compliance period" className="w-auto" value={days} onChange={(e) => setDays(e.target.value)}>
          {[7, 14, 30].map((d) => <option key={d} value={d}>Last {d} days</option>)}
        </Select>
      </div>
      {error && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
      {!data && loading && <Skeleton className="h-48" />}
      {data && data.outlets.length === 0 && <p className="text-sm text-ink-muted">No outlets to show.</p>}
      {data && (
        <>
          <p className="text-xs text-ink-muted">From {data.range.date_from} to {data.range.date_to}. Work still waiting for its deadline is not counted.</p>
          <div className="grid gap-4 xl:grid-cols-2">
            {[...data.outlets].filter((o) => !idle(o)).sort((a, b) => worst(a) - worst(b) || (b.failed_readings ?? 0) - (a.failed_readings ?? 0)).map((o) => <OutletCard key={o.location_id} o={o} />)}
          </div>
          {data.outlets.some(idle) && (
            <p className="text-sm text-ink-muted">Nothing scheduled in this period: {data.outlets.filter(idle).map((o) => o.location).join(', ')}.</p>
          )}
        </>
      )}
    </section>
  )
}
