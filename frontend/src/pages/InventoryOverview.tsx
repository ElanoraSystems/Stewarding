import { AlertTriangle, ArrowLeftRight, Boxes, PackageMinus, TrendingDown, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ColumnChart } from '@/components/charts'
import { KpiCard } from '@/components/KpiCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { qs, useApi } from '@/lib/useApi'
import { useAllItems, type Item } from '@/lib/useItems'

interface Props {
  locationId: number | null
  totalItems: number
  totalValue?: number
}

interface Insights {
  movement: { date: string; in: number; out: number }[]
  totals: { in: number; out: number; breakage_units: number; breakage_cost: number }
  transfers: { requested: number }
}

interface Txn { id: number; item_id: number; txn_type: string; qty_delta: number; occurred_at: string; user: string | null }

const SERIES = [
  { key: 'in', label: 'Stock in', className: 'bg-brand' },
  { key: 'out', label: 'Stock out', className: 'bg-warn' },
]

const when = (iso: string) => new Date(iso.endsWith('Z') ? iso : `${iso}Z`).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function InventoryOverview({ locationId, totalItems, totalValue }: Props) {
  const { byId } = useAllItems()
  const insights = useApi<Insights>(`/stock/insights${qs({ location_id: locationId })}`)
  const recent = useApi<{ items: Txn[] }>(`/inventory/transactions${qs({ location_id: locationId, size: 5 })}`)
  const low = useApi<{ total: number; items: Item[] }>(`/inventory/items${qs({ location_id: locationId, low_only: true, size: 100 })}`)
  const empty = low.data?.items.filter((i) => i.qty <= 0).length ?? 0
  const totals = insights.data?.totals

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Total items" value={totalItems} icon={Boxes} />
        {totalValue !== undefined && <KpiCard label="Stock value" value={totalValue.toFixed(2)} hint="At weighted average cost" icon={Wallet} />}
        <KpiCard label="Low stock items" value={low.data?.total ?? '-'} tone={low.data?.total ? 'warn' : 'ok'} icon={TrendingDown} />
        <KpiCard label="Out of stock" value={low.data ? empty : '-'} tone={empty ? 'critical' : 'ok'} icon={PackageMinus} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Inventory statistics</CardTitle>
            {totals && <p className="text-xs text-ink-muted">Last 30 days: {totals.in} in, {totals.out} out</p>}
          </CardHeader>
          <CardContent>
            {insights.data ? <ColumnChart data={insights.data.movement} labelKey="date" series={SERIES} /> : <div className="h-40 animate-pulse rounded-lg bg-surface-muted" />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Alerts</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <AlertRow icon={AlertTriangle} tone="text-danger" text={`${empty} items out of stock`} />
            <AlertRow icon={TrendingDown} tone="text-warn" text={`${low.data?.total ?? 0} items at or below minimum`} />
            <AlertRow icon={ArrowLeftRight} tone="text-brand" text={`${insights.data?.transfers.requested ?? 0} transfers requested`} to="/stock-movements" />
            <AlertRow icon={PackageMinus} tone="text-warn" text={`${totals?.breakage_units ?? 0} units broken or damaged`} to="/breakage" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Recent activity</CardTitle></CardHeader>
        <CardContent>
          {recent.data?.items.length === 0 && <p className="text-sm text-ink-muted">No stock movements yet.</p>}
          <ul className="divide-y divide-border">
            {recent.data?.items.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span><span className="font-medium">{byId.get(t.item_id)?.name ??`Item ${t.item_id}`}</span> <span className="text-ink-muted">{t.txn_type.replace('_', ' ')}{t.user ? ` by ${t.user}` : ''}</span></span>
                <span className="flex items-center gap-3">
                  <span className={t.qty_delta > 0 ? 'font-medium text-ok' : 'font-medium text-danger'}>{t.qty_delta > 0 ? '+' : ''}{t.qty_delta}</span>
                  <span className="hidden text-xs text-ink-muted sm:inline">{when(t.occurred_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

function AlertRow({ icon: Icon, tone, text, to }: { icon: typeof AlertTriangle; tone: string; text: string; to?: string }) {
  const body = (
    <span className="flex items-center gap-2 rounded-lg bg-surface-muted px-3 py-2 text-sm">
      <Icon className={`h-4 w-4 shrink-0 ${tone}`} aria-hidden />{text}
    </span>
  )
  return to ? <Link to={to} className="block hover:opacity-80">{body}</Link> : body
}
