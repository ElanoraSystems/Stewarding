export interface TrendPoint {
  recorded_at: string
  value: number
  passed: boolean
  warning?: boolean
}

interface Props {
  points: TrendPoint[]
  min: number | null
  max: number | null
  warnMin?: number | null
  warnMax?: number | null
  unit?: string | null
}

const W = 600
const H = 200
const PAD = { left: 44, right: 12, top: 12, bottom: 24 }
const DAY_MS = 86_400_000

const dayLabel = (ms: number) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date(ms))
const when = (iso: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(iso))

/** A line of readings over time with the pass limits (red, dashed) and the amber warning levels (amber, dotted); a failed reading is a red cross, not only a red colour. */
export function LimitTrend({ points, min, max, warnMin = null, warnMax = null, unit }: Props) {
  if (points.length === 0) return <p className="py-6 text-center text-sm text-ink-muted">No readings in this period.</p>
  const times = points.map((p) => new Date(p.recorded_at).getTime())
  const t0 = Math.min(...times)
  const t1 = Math.max(...times, t0 + 1)
  const levels = [min, max, warnMin, warnMax].filter((v): v is number => v !== null)
  const values = [...points.map((p) => p.value), ...levels]
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const x = (t: number) => PAD.left + (points.length === 1 ? (W - PAD.left - PAD.right) / 2 : ((t - t0) / (t1 - t0)) * (W - PAD.left - PAD.right))
  const y = (v: number) => PAD.top + (1 - (v - lo + span * 0.05) / (span * 1.1)) * (H - PAD.top - PAD.bottom)
  const failed = points.filter((p) => !p.passed).length
  const u = unit ? ` ${unit}` : ''
  const lines = [
    { v: max, name: 'Highest allowed', cls: 'stroke-danger', dash: '6 4' },
    { v: min, name: 'Lowest allowed', cls: 'stroke-danger', dash: '6 4' },
    { v: warnMax, name: 'Amber from', cls: 'stroke-warn', dash: '2 3' },
    { v: warnMin, name: 'Amber down to', cls: 'stroke-warn', dash: '2 3' },
  ].filter((l): l is typeof l & { v: number } => l.v !== null)
  const ticks = [lo, (lo + hi) / 2, hi]
  const days = Math.max(1, Math.round((t1 - t0) / DAY_MS))
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-52 w-full" role="img"
        aria-label={`Trend of ${points.length} readings over ${days} day${days === 1 ? '' : 's'}, ${failed} outside the limits. Latest ${points[points.length - 1].value}${u}.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={0.5} />
            <text x={PAD.left - 6} y={y(t) + 3} textAnchor="end" className="fill-ink-muted text-[10px]">{+t.toFixed(1)}</text>
          </g>
        ))}
        {lines.map((l) => (
          <line key={l.name} x1={PAD.left} x2={W - PAD.right} y1={y(l.v)} y2={y(l.v)} className={l.cls} strokeWidth={1.5} strokeDasharray={l.dash}>
            <title>{`${l.name}: ${l.v}${u}`}</title>
          </line>
        ))}
        <polyline fill="none" className="stroke-brand" strokeWidth={2} strokeLinejoin="round"
          points={points.map((p, i) => `${x(times[i])},${y(p.value)}`).join(' ')} />
        {points.map((p, i) => {
          const cx = x(times[i])
          const cy = y(p.value)
          const tip = <title>{`${when(p.recorded_at)}: ${p.value}${u}${p.passed ? (p.warning ? ' (amber warning)' : '') : ' (failed)'}`}</title>
          return p.passed
            ? <circle key={p.recorded_at + i} cx={cx} cy={cy} r={3} className={p.warning ? 'fill-warn' : 'fill-brand'}>{tip}</circle>
            : <path key={p.recorded_at + i} d={`M${cx - 4},${cy - 4}L${cx + 4},${cy + 4}M${cx + 4},${cy - 4}L${cx - 4},${cy + 4}`} className="stroke-danger" strokeWidth={2.5} fill="none">{tip}</path>
        })}
        <text x={PAD.left} y={H - 6} className="fill-ink-muted text-[10px]">{dayLabel(t0)}</text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end" className="fill-ink-muted text-[10px]">{dayLabel(t1)}</text>
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
        {lines.map((l) => <li key={l.name}><span className={l.cls === 'stroke-danger' ? 'text-danger' : 'text-warn'} aria-hidden>{l.dash === '6 4' ? '- - -' : '· · ·'}</span> {l.name} {l.v}{u}</li>)}
        <li><span className="font-bold text-danger" aria-hidden>×</span> Failed reading{failed === 1 ? '' : 's'}: {failed}</li>
      </ul>
    </div>
  )
}
