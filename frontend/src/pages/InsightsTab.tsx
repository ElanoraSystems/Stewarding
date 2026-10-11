import { useState } from 'react'
import { ColumnChart, QuantityBars } from '@/components/charts'
import { KpiCard } from '@/components/KpiCard'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/table'
import { PRESETS, type Range } from '@/lib/dates'
import { qs, useApi } from '@/lib/useApi'

interface Insights {
  range: { grain: 'day' | 'month' }
  movement: { date: string; in: number; out: number }[]
  movement_by_type: { label: string; value: number }[]
  breakage_trend: { period: string; incidents: number; qty: number; est_cost: number }[]
  breakage_by_reason: { label: string; value: number }[]
  breakage_top_items: { label: string; value: number }[]
  transfers: { requested: number; completed: number; rejected: number; units: number }
  transfer_routes: { label: string; value: number; sub: string }[]
  totals: { in: number; out: number; breakage_units: number; breakage_cost: number }
}

export function InsightsTab() {
  const [preset, setPreset] = useState('last30')
  const [locationId, setLocationId] = useState<number | null>(null)
  const range = (PRESETS.find((p) => p.key === preset) ?? PRESETS[0]).range() as Range
  const { data, error } = useApi<Insights>(`/stock/insights${qs({ location_id: locationId, date_from: range[0], date_to: range[1] })}`)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.filter((p) => ['today', 'week', 'month', 'lastmonth', 'last30'].includes(p.key)).map((p) => (
          <Button key={p.key} size="sm" variant={preset === p.key ? 'default' : 'outline'} onClick={() => setPreset(p.key)}>{p.label}</Button>
        ))}
        <LocationSelect allowAll value={locationId} onChange={setLocationId} />
      </div>
      {error && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
      {!data ? <Skeleton className="h-64 w-full" /> : (
        <>
          <section aria-label="Key figures" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiCard label="Stock in" value={data.totals.in} hint="receipts, returns, transfers in" tone="ok" />
            <KpiCard label="Stock out" value={data.totals.out} hint="issues, breakage, transfers out" />
            <KpiCard label="Breakage units" value={data.totals.breakage_units} hint={`Est. cost ${data.totals.breakage_cost.toFixed(2)}`} tone={data.totals.breakage_units ? 'warn' : 'default'} />
            <KpiCard label="Transfers completed" value={data.transfers.completed} hint={`${data.transfers.units} units moved`} />
            <KpiCard label="Transfers waiting" value={data.transfers.requested} hint={`${data.transfers.rejected} rejected`} tone={data.transfers.requested ? 'warn' : 'default'} />
          </section>
          <section aria-label="Charts" className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Stock in and out {data.range.grain === 'month' ? 'by month' : 'by day'}</CardTitle></CardHeader>
              <CardContent><ColumnChart data={data.movement} labelKey="date" series={[{ key: 'in', label: 'In', className: 'bg-ok' }, { key: 'out', label: 'Out', className: 'bg-brand' }]} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Breakage trend</CardTitle></CardHeader>
              <CardContent><ColumnChart data={data.breakage_trend} labelKey="period" series={[{ key: 'qty', label: 'Units broken', className: 'bg-danger' }, { key: 'incidents', label: 'Incidents', className: 'bg-warn' }]} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Movement by type (units)</CardTitle></CardHeader>
              <CardContent><QuantityBars items={data.movement_by_type} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Transfers between locations (units)</CardTitle></CardHeader>
              <CardContent><QuantityBars items={data.transfer_routes} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Breakage by reason (units)</CardTitle></CardHeader>
              <CardContent><QuantityBars items={data.breakage_by_reason} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Most broken items (units)</CardTitle></CardHeader>
              <CardContent><QuantityBars items={data.breakage_top_items} /></CardContent>
            </Card>
          </section>
        </>
      )}
    </div>
  )
}
