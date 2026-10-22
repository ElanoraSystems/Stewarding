import { Boxes, PackageMinus, ShoppingCart, Wallet } from 'lucide-react'
import { useState } from 'react'
import { KpiCard } from '@/components/KpiCard'
import { LocationSelect } from '@/components/LocationSelect'
import { Input } from '@/components/ui/input'
import { EmptyState, Skeleton, Table, Td, Th } from '@/components/ui/table'
import { qs, useApi } from '@/lib/useApi'

interface Totals {
  opening_value: number
  purchases: number
  returns: number
  transfers_in: number
  transfers_out: number
  closing_value: number
  cost_consumed: number
  issued: number
  breakage_damage: number
  count_adjustments: number
}

interface CategoryLine extends Totals {
  category: string
  items: number
  share: number
}

interface ItemLine extends Totals {
  item_id: number
  code: string
  name: string
  category: string
  average_cost: number | null
}

interface Report {
  totals: Totals
  by_category: CategoryLine[]
  rows?: ItemLine[]
  locations?: { location_id: number; location: string; totals: Totals }[]
}

const money = (n: number) => n.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const thisMonth = () => new Date().toLocaleDateString('en-CA').slice(0, 7)

function period(month: string) {
  const [year, mon] = month.split('-').map(Number)
  const last = new Date(year, mon, 0).getDate()
  return { date_from: `${month}-01`, date_to: `${month}-${String(last).padStart(2, '0')}` }
}

export function CostTab() {
  const [locationId, setLocationId] = useState<number | null>(null)
  const [month, setMonth] = useState(thisMonth())
  const { data, loading } = useApi<Report>(`/stock/cost-report${qs({ ...period(month), location_id: locationId })}`)
  const t = data?.totals

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <LocationSelect allowAll value={locationId} onChange={setLocationId} />
        <Input aria-label="Month" type="month" className="w-auto" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
      </div>

      {loading && !data ? <Skeleton className="h-28 w-full" /> : t && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard icon={Wallet} label="Opening value" value={money(t.opening_value)} />
          <KpiCard icon={ShoppingCart} label="Purchases" value={money(t.purchases)} />
          <KpiCard icon={Boxes} label="Closing value" value={money(t.closing_value)} />
          <KpiCard icon={PackageMinus} label="Cost consumed" value={money(t.cost_consumed)} tone="warn" />
        </div>
      )}

      {data && data.by_category.length === 0 && <EmptyState title="No stock movement in this period" />}
      {data && data.by_category.length > 0 && (
        <>
          <h2 className="text-lg font-semibold">By category</h2>
          <Table>
            <thead><tr><Th>Category</Th><Th className="text-right">Items</Th><Th className="text-right">Opening</Th><Th className="text-right">Purchases</Th><Th className="text-right">Closing</Th><Th className="text-right">Cost consumed</Th><Th className="text-right">Share</Th></tr></thead>
            <tbody>
              {data.by_category.map((c) => (
                <tr key={c.category}>
                  <Td className="font-medium">{c.category}</Td>
                  <Td className="text-right tabular-nums">{c.items}</Td>
                  <Td className="text-right tabular-nums">{money(c.opening_value)}</Td>
                  <Td className="text-right tabular-nums">{money(c.purchases)}</Td>
                  <Td className="text-right tabular-nums">{money(c.closing_value)}</Td>
                  <Td className="text-right tabular-nums">{money(c.cost_consumed)}</Td>
                  <Td className="text-right tabular-nums">{c.share}%</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}

      {data?.locations && data.locations.length > 0 && (
        <>
          <h2 className="text-lg font-semibold">By location</h2>
          <Table>
            <thead><tr><Th>Location</Th><Th className="text-right">Opening</Th><Th className="text-right">Purchases</Th><Th className="text-right">Closing</Th><Th className="text-right">Cost consumed</Th></tr></thead>
            <tbody>
              {data.locations.map((l) => (
                <tr key={l.location_id}>
                  <Td className="font-medium">{l.location}</Td>
                  <Td className="text-right tabular-nums">{money(l.totals.opening_value)}</Td>
                  <Td className="text-right tabular-nums">{money(l.totals.purchases)}</Td>
                  <Td className="text-right tabular-nums">{money(l.totals.closing_value)}</Td>
                  <Td className="text-right tabular-nums">{money(l.totals.cost_consumed)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}

      {data?.rows && data.rows.length > 0 && (
        <>
          <h2 className="text-lg font-semibold">By item</h2>
          <Table>
            <thead><tr><Th>Item</Th><Th>Category</Th><Th className="text-right">Average cost</Th><Th className="text-right">Opening</Th><Th className="text-right">Purchases</Th><Th className="text-right">Closing</Th><Th className="text-right">Cost consumed</Th></tr></thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.item_id}>
                  <Td className="font-medium">{r.code} - {r.name}</Td>
                  <Td>{r.category}</Td>
                  <Td className="text-right tabular-nums">{r.average_cost != null ? money(r.average_cost) : '-'}</Td>
                  <Td className="text-right tabular-nums">{money(r.opening_value)}</Td>
                  <Td className="text-right tabular-nums">{money(r.purchases)}</Td>
                  <Td className="text-right tabular-nums">{money(r.closing_value)}</Td>
                  <Td className="text-right tabular-nums">{money(r.cost_consumed)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </div>
  )
}
