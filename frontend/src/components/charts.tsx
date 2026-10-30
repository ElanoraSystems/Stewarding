import { cn } from '@/lib/utils'

export function BarList({ items, unit = '%' }: { items: { label: string; value: number | null; sub?: string }[]; unit?: string }) {
  if (items.length === 0) return <p className="py-6 text-center text-sm text-ink-muted">No data for this selection.</p>
  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const value = item.value ?? 0
        const tone = item.value === null ? 'bg-border' : item.value >= 90 ? 'bg-ok' : item.value >= 70 ? 'bg-warn' : 'bg-danger'
        return (
          <li key={item.label}>
            <div className="flex justify-between gap-2 text-sm">
              <span className="truncate font-medium">{item.label}</span>
              <span className="tabular-nums text-ink-muted">{item.value === null ? 'n/a' : `${item.value}${unit}`}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded bg-surface-muted" role="img" aria-label={`${item.label} ${item.value ?? 'no data'}${unit}`}>
              <div className={cn('h-full rounded', tone)} style={{ width: `${Math.min(value, 100)}%` }} />
            </div>
            {item.sub && <p className="mt-0.5 text-xs text-ink-muted">{item.sub}</p>}
          </li>
        )
      })}
    </ul>
  )
}

interface Series {
  key: string
  label: string
  className: string
}

interface ColumnChartProps {
  data: Record<string, string | number>[]
  labelKey: string
  series: Series[]
  height?: number
  format?: (n: number) => string  // how a value reads in the tooltip and legend, for example as money
  empty?: string
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-10-28" reads 28 Oct, "2026-10" reads Oct 2026; anything else is shown as it came. */
function chartLabel(raw: string): string {
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw)
  if (day) return `${Number(day[3])} ${MONTHS[Number(day[2]) - 1]}`
  const month = /^(\d{4})-(\d{2})$/.exec(raw)
  return month ? `${MONTHS[Number(month[2]) - 1]} ${month[1]}` : raw
}

/** The next round number at or above the largest value, so the scale reads 0, 25, 50, 75, 100 rather than odd figures. */
function niceMax(value: number): number {
  const size = 10 ** Math.floor(Math.log10(Math.max(value, 1)))
  return [1, 2, 2.5, 5, 10].map((m) => m * size).find((m) => m >= value) ?? 10 * size
}

const compact = (n: number) => (n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(1)}M` : n >= 10_000 ? `${+(n / 1000).toFixed(1)}k` : String(+n.toFixed(2)))

/** Bars by day or month with a value scale, readable date labels and a pop-up with the exact figures on hover or focus. */
export function ColumnChart({ data, labelKey, series, height = 180, format = (n) => n.toLocaleString(), empty = 'Nothing recorded in this period.' }: ColumnChartProps) {
  const values = data.flatMap((d) => series.map((s) => Number(d[s.key]) || 0))
  if (values.every((v) => v === 0)) return <p className="py-10 text-center text-sm text-ink-muted">{empty}</p>
  const top = niceMax(Math.max(...values))
  const ticks = [1, 0.75, 0.5, 0.25, 0]
  const every = Math.ceil(data.length / 6)  // about six date labels fit whatever the width, even on a phone
  const total = (key: string) => data.reduce((sum, d) => sum + (Number(d[key]) || 0), 0)
  return (
    <div>
      <div className="flex gap-2" role="img" aria-label={`${series.map((s) => s.label).join(' and ')} by ${labelKey}`}>
        <div className="relative w-10 shrink-0 text-right text-[11px] tabular-nums text-ink-muted" style={{ height }}>
          {ticks.map((t) => <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: `${(1 - t) * 100}%` }}>{compact(top * t)}</span>)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="relative" style={{ height }}>
            {ticks.map((t) => <div key={t} className="absolute inset-x-0 border-t border-border/70" style={{ top: `${(1 - t) * 100}%` }} />)}
            <div className="absolute inset-0 flex items-end gap-[3px]">
              {data.map((d, i) => {
                const place = i < data.length / 3 ? 'left-0' : i > (data.length * 2) / 3 ? 'right-0' : 'left-1/2 -translate-x-1/2'
                return (
                  <div key={String(d[labelKey])} tabIndex={0} className="group relative flex h-full min-w-0 flex-1 items-end justify-center gap-px rounded-sm outline-offset-2 hover:bg-surface-muted/60 focus:bg-surface-muted/60">
                    {series.map((s) => (
                      <div key={s.key} className={cn('w-full max-w-5 rounded-t-sm', s.className)}
                        style={{ height: `${((Number(d[s.key]) || 0) / top) * 100}%`, minHeight: Number(d[s.key]) ? 3 : 0 }} />
                    ))}
                    <div className={cn('pointer-events-none absolute bottom-full z-10 mb-1 hidden w-max min-w-28 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-lg group-hover:block group-focus:block', place)}>
                      <p className="font-semibold">{chartLabel(String(d[labelKey]))}</p>
                      {series.map((s) => (
                        <p key={s.key} className="flex items-center justify-between gap-3">
                          <span className="flex items-center gap-1.5"><span className={cn('inline-block h-2 w-2 rounded-sm', s.className)} />{s.label}</span>
                          <span className="font-medium tabular-nums">{format(Number(d[s.key]) || 0)}</span>
                        </p>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
          <div className="mt-1 flex gap-[3px] text-[11px] text-ink-muted">
            {data.map((d, i) => (
              <span key={String(d[labelKey])} className="relative h-4 min-w-0 flex-1">
                {i % every === 0 && <span className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap">{chartLabel(String(d[labelKey]))}</span>}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-muted">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className={cn('inline-block h-2.5 w-2.5 rounded-sm', s.className)} />{s.label}: <span className="font-semibold text-ink tabular-nums">{format(total(s.key))}</span> in total
          </span>
        ))}
      </div>
    </div>
  )
}

export function TrendLine({ points }: { points: { label: string; value: number | null }[] }) {
  const width = 300
  const height = 100
  const step = points.length > 1 ? width / (points.length - 1) : 0
  const known = points.map((p, i) => (p.value === null ? null : { x: i * step, y: height - (p.value / 100) * height, p }))
  const path = known.filter((k) => k !== null).map((k) => `${k.x},${k.y}`).join(' ')
  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full" role="img"
        aria-label={`Completion trend, ${points.filter((p) => p.value !== null).length} days with data`}>
        {[0, 50, 100].map((g) => <line key={g} x1={0} x2={width} y1={height - g} y2={height - g} className="stroke-border" strokeWidth={0.5} />)}
        {path && <polyline points={path} fill="none" className="stroke-brand" strokeWidth={2} strokeLinejoin="round" />}
        {known.map((k) => k && <circle key={k.p.label} cx={k.x} cy={k.y} r={2.5} className="fill-brand"><title>{`${k.p.label}: ${k.p.value}%`}</title></circle>)}
      </svg>
      <div className="flex justify-between text-[10px] text-ink-muted">
        <span>{points[0]?.label.slice(-5)}</span>
        <span>{points[points.length - 1]?.label.slice(-5)}</span>
      </div>
    </div>
  )
}

/** Horizontal bars sized against the largest value, for counts of units rather than percentages. */
export function QuantityBars({ items, unit = '' }: { items: { label: string; value: number; sub?: string }[]; unit?: string }) {
  if (items.length === 0) return <p className="py-6 text-center text-sm text-ink-muted">Nothing recorded for this selection.</p>
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.label}>
          <div className="flex justify-between gap-2 text-sm">
            <span className="truncate font-medium">{item.label}</span>
            <span className="tabular-nums text-ink-muted">{item.value}{unit}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded bg-surface-muted" role="img" aria-label={`${item.label} ${item.value}${unit}`}>
            <div className="h-full rounded bg-brand" style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
          {item.sub && <p className="mt-0.5 text-xs text-ink-muted">{item.sub}</p>}
        </li>
      ))}
    </ul>
  )
}

/** A line of prices over time, scaled between the lowest and highest price so small moves are visible; hover a point for its details. */
export function PriceLine({ points, format }: { points: { label: string; value: number; sub?: string }[]; format: (n: number) => string }) {
  if (points.length === 0) return <p className="py-6 text-center text-sm text-ink-muted">No priced invoices for this item yet.</p>
  const width = 320
  const height = 120
  const pad = 8
  const low = Math.min(...points.map((p) => p.value))
  const high = Math.max(...points.map((p) => p.value))
  const span = high - low || 1
  const step = points.length > 1 ? (width - pad * 2) / (points.length - 1) : 0
  const at = (p: { value: number }, i: number) => ({ x: points.length > 1 ? pad + i * step : width / 2, y: pad + (1 - (p.value - low) / span) * (height - pad * 2) })
  const line = points.map((p, i) => { const { x, y } = at(p, i); return `${x},${y}` }).join(' ')
  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-36 w-full" role="img" aria-label={`Price from ${format(points[0].value)} to ${format(points[points.length - 1].value)} over ${points.length} invoices`}>
        {[0, 0.5, 1].map((g) => <line key={g} x1={0} x2={width} y1={pad + g * (height - pad * 2)} y2={pad + g * (height - pad * 2)} className="stroke-border" strokeWidth={0.5} />)}
        {points.length > 1 && <polyline points={line} fill="none" className="stroke-brand" strokeWidth={2} strokeLinejoin="round" />}
        {points.map((p, i) => { const { x, y } = at(p, i); return <circle key={`${p.label}-${i}`} cx={x} cy={y} r={3.5} className="fill-brand"><title>{`${p.label}: ${format(p.value)}${p.sub ? ` (${p.sub})` : ''}`}</title></circle> })}
      </svg>
      <div className="flex justify-between text-[11px] text-ink-muted">
        <span>{points[0].label}</span><span>High {format(high)} - Low {format(low)}</span><span>{points[points.length - 1].label}</span>
      </div>
    </div>
  )
}
