import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { greeting } from '@/components/HeroCard'
import { Badge } from '@/components/ui/badge'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtTime, hoursMinutes } from '@/lib/format'
import { useApi } from '@/lib/useApi'
import { useTick } from '@/lib/useTick'
import { MyShiftCard } from '@/pages/MyShiftCard'

interface Day {
  id: number
  local_date: string
  check_in_at: string
  check_out_at: string | null
  late_minutes: number
  payable_minutes: number | null
  open: boolean
  missed_checkout: boolean
}

const WEEKDAY = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' })

/** The screen people open on their phone to check in and out: a clock, the check-in card, the week so far and the last days. */
export function CheckInPage() {
  const now = new Date(useTick(true))
  const { me } = useAuth()
  const recent = useApi<{ items: Day[] }>('/attendance/mine?size=7')
  const first = (me?.employee?.name ?? '').split(' ')[0]

  const days = (recent.data?.items ?? []).slice(0, 7).reverse()
  const minutesOf = (d: Day) => (d.open ? Math.max(0, Math.round((now.getTime() - new Date(d.check_in_at).getTime()) / 60000)) : d.payable_minutes ?? 0)
  const longest = Math.max(60, ...days.map(minutesOf))
  const total = days.reduce((sum, d) => sum + minutesOf(d), 0)

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="ci-rise flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <p className="text-sm text-ink-muted">{new Intl.DateTimeFormat('en-GB', { dateStyle: 'full' }).format(now)}</p>
          <h1 className="text-2xl font-semibold">Check in &amp; out</h1>
          <p className="text-ink-muted">{greeting(now)}{first ? `, ${first}` : ''}</p>
        </div>
        <p className="text-5xl font-bold tabular-nums tracking-tight" aria-label="Current time">
          {new Intl.DateTimeFormat('en-GB', { timeStyle: 'short' }).format(now)}
          <span className="ml-1.5 text-xl font-semibold tracking-normal text-ink-muted">:{String(now.getSeconds()).padStart(2, '0')}</span>
        </p>
      </header>

      <MyShiftCard onChange={recent.reload} />
      {me?.permissions.includes('settings.manage') && (
        <p className="text-sm">
          <Link to="/settings/attendance" className="font-medium text-brand-deep hover:underline">Check-in rules</Link>
          <span className="text-ink-muted"> - face check, location accuracy and missed check-out</span>
        </p>
      )}

      {days.length > 0 && (
        <section aria-label="This week" className="ci-rise rounded-3xl border border-border bg-surface p-5 [animation-delay:0.1s]">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-lg font-semibold">Your week</h2>
            <p className="text-sm text-ink-muted">{hoursMinutes(total)} worked</p>
          </div>
          <div className="mt-4 flex h-24 items-end gap-2.5">
            {days.map((d, i) => (
              <div key={d.id} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
                <div title={`${fmtDate(d.local_date)}: ${hoursMinutes(minutesOf(d))}`} aria-hidden
                  className={d.open ? 'ci-bar w-full max-w-7 rounded-b-sm rounded-t-lg bg-[repeating-linear-gradient(45deg,var(--color-brand),var(--color-brand)_4px,#7fd6c2_4px,#7fd6c2_8px)]' : 'ci-bar w-full max-w-7 rounded-b-sm rounded-t-lg bg-brand'}
                  style={{ height: `${Math.max(4, (minutesOf(d) / longest) * 100)}%`, animationDelay: `${0.2 + i * 0.07}s` }} />
                <span className="text-xs font-semibold text-ink-muted">{WEEKDAY.format(new Date(`${d.local_date}T00:00:00Z`))}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3" aria-label="Recent days">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Your last days</h2>
          <Link to="/attendance" className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-brand-deep hover:underline">
            All attendance and leave <ChevronRight aria-hidden className="h-4 w-4" />
          </Link>
        </div>
        {!recent.data ? <Skeleton className="h-24 w-full" /> : recent.data.items.length === 0 ? <EmptyState title="No attendance yet" /> : (
          <ul className="space-y-3">
            {recent.data.items.map((d, i) => (
              <li key={d.id} className="ci-rise flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-surface px-5 py-4" style={{ animationDelay: `${0.15 + i * 0.06}s` }}>
                <div>
                  <p className="font-medium">{fmtDate(d.local_date)}</p>
                  <p className="text-sm text-ink-muted">{fmtTime(d.check_in_at)} to {d.open ? 'on duty' : fmtTime(d.check_out_at)}</p>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {d.late_minutes > 0 && <Badge tone="warn">Late {d.late_minutes}m</Badge>}
                  {d.missed_checkout && <Badge tone="critical">Missed checkout</Badge>}
                  <span className="text-sm font-semibold tabular-nums">{d.open ? 'Now' : hoursMinutes(d.payable_minutes)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
