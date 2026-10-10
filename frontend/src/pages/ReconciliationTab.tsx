import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Input } from '@/components/ui/input'
import { EmptyState, Table, Td, Th } from '@/components/ui/table'
import { qs, useApi } from '@/lib/useApi'

interface Row {
  item_id: number
  code: string
  name: string
  opening: number
  opening_stock: number
  receipts: number
  returns: number
  issues: number
  breakage_damage: number
  transfers_in: number
  transfers_out: number
  adjustments: number
  closing: number
  counted_qty: number | null
  count_variance: number | null
  value: number | null
}

export function ReconciliationTab() {
  const [locationId, setLocationId] = useState<number | null>(null)
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const { data } = useApi<{ rows: Row[]; total_closing: number }>(
    locationId && month ? `/stock/reconciliation${qs({ location_id: locationId, month })}` : null,
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <LocationSelect value={locationId} onChange={setLocationId} />
        <Input aria-label="Month" type="month" className="w-auto" value={month} onChange={(e) => setMonth(e.target.value)} />
      </div>
      <p className="text-sm text-ink-muted">Opening + movements = closing. Every figure is summed from the immutable stock ledger.</p>
      <Table>
        <thead>
          <tr>
            <Th>Item</Th><Th className="text-right">Opening</Th><Th className="text-right">Opening stock</Th><Th className="text-right">Receipts</Th>
            <Th className="text-right">Issues</Th><Th className="text-right">Breakage</Th><Th className="text-right">Transfers</Th>
            <Th className="text-right">Adjust.</Th><Th className="text-right">Closing</Th><Th className="text-right">Counted</Th>
          </tr>
        </thead>
        <tbody>
          {data?.rows.map((r) => (
            <tr key={r.item_id}>
              <Td className="font-medium">{r.code} - {r.name}</Td>
              <Td className="text-right tabular-nums">{r.opening}</Td>
              <Td className="text-right tabular-nums">{r.opening_stock}</Td>
              <Td className="text-right tabular-nums">{r.receipts + r.returns}</Td>
              <Td className="text-right tabular-nums">{r.issues}</Td>
              <Td className="text-right tabular-nums">{r.breakage_damage}</Td>
              <Td className="text-right tabular-nums">{r.transfers_in + r.transfers_out}</Td>
              <Td className="text-right tabular-nums">{r.adjustments}</Td>
              <Td className="text-right font-medium tabular-nums">{r.closing}</Td>
              <Td className="text-right tabular-nums">{r.counted_qty ?? '-'}{r.count_variance ? ` (${r.count_variance})` : ''}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.rows.length === 0 && <EmptyState title="No stock activity for this month" />}
    </div>
  )
}
