import { useState } from 'react'
import { LimitTrend, type TrendPoint } from '@/components/LimitTrend'
import { Select } from '@/components/ui/select'
import { qs, useApi } from '@/lib/useApi'

interface Trend {
  unit: string | null
  min_value: number | null
  max_value: number | null
  warn_min: number | null
  warn_max: number | null
  truncated: boolean
  points: TrendPoint[]
}

/** The recent readings of one number check as a line, with its limits drawn on it. */
export function PointTrend({ equipmentId, scheduleId, name }: { equipmentId: number; scheduleId: number; name: string }) {
  const [days, setDays] = useState('14')
  const { data, loading, error } = useApi<Trend>(`/monitoring/trend${qs({ equipment_id: equipmentId, schedule_id: scheduleId, days })}`)
  return (
    <div className="mt-3 w-full space-y-2 rounded-xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">{name}: readings over time</p>
        <Select aria-label={`Period for ${name}`} className="w-auto" value={days} onChange={(e) => setDays(e.target.value)}>
          {[7, 14, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}
        </Select>
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {!data && loading && <p className="py-6 text-center text-sm text-ink-muted">Loading...</p>}
      {data && (
        <>
          <LimitTrend points={data.points} min={data.min_value} max={data.max_value} warnMin={data.warn_min} warnMax={data.warn_max} unit={data.unit} />
          {data.truncated && <p className="text-xs text-ink-muted">There are more readings than fit here. The most recent ones are shown; pick a shorter period to see them all.</p>}
        </>
      )}
    </div>
  )
}
