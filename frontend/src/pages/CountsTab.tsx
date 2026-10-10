import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { useAllItems, type Item } from '@/lib/useItems'

interface Count {
  id: number
  location_id: number
  kind: string
  counted_at: string
  status: string
  lines: { item_id: number; system_qty: number; counted_qty: number; variance: number }[]
}

export function CountsTab() {
  const { me } = useAuth()
  const run = useRun()
  const canApprove = me?.permissions.includes('stock.approve') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const [kind, setKind] = useState<'crockery' | 'smallware'>('crockery')
  const [entered, setEntered] = useState<Record<number, string>>({})
  const { items, byId } = useAllItems()
  const counts = useApi<Count[]>(locationId ? `/stock/counts${qs({ location_id: locationId })}` : null)
  const rows = items.filter((i: Item) => i.kind === kind)

  async function submit() {
    const lines = Object.entries(entered).filter(([, v]) => v !== '').map(([id, v]) => ({ item_id: Number(id), counted_qty: Number(v) }))
    const ok = await run(() => api('/stock/counts', { body: { location_id: locationId, kind, lines } }), 'Count saved - post it to apply variances')
    if (ok) {
      setEntered({})
      counts.reload()
    }
  }

  async function post(count: Count) {
    if (await run(() => api(`/stock/counts/${count.id}/post`, { method: 'POST' }), 'Count posted')) counts.reload()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <LocationSelect value={locationId} onChange={setLocationId} />
        <Select aria-label="Inventory type" className="w-auto" value={kind} onChange={(e) => { setKind(e.target.value as typeof kind); setEntered({}) }}>
          <option value="crockery">Crockery</option>
          <option value="smallware">Kitchen smallware</option>
        </Select>
      </div>
      <Card>
        <CardHeader><CardTitle>Physical count</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-ink-muted">Enter what you counted. Items left blank are not part of this count.</p>
          <Table>
            <thead><tr><Th>Item</Th><Th className="text-right">System</Th><Th>Counted</Th></tr></thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id}>
                  <Td>{i.code} - {i.name}</Td>
                  <Td className="text-right tabular-nums">{locationId ? (i.by_location[String(locationId)] ?? 0) : '-'}</Td>
                  <Td><Input aria-label={`Counted ${i.name}`} type="number" min={0} className="w-28" value={entered[i.id] ?? ''} onChange={(e) => setEntered((v) => ({ ...v, [i.id]: e.target.value }))} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Button disabled={!locationId || !Object.values(entered).some((v) => v !== '')} onClick={submit}>Save count</Button>
        </CardContent>
      </Card>

      <h2 className="text-lg font-semibold">Counts</h2>
      {counts.data?.length === 0 && <EmptyState title="No counts at this location" />}
      {counts.data?.map((c) => {
        const variances = c.lines.filter((l) => l.variance !== 0)
        return (
          <Card key={c.id}>
            <CardContent className="space-y-2 pt-5 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">Count #{c.id} - {c.kind} - {fmtDateTime(c.counted_at)}</span>
                <Badge tone={c.status === 'posted' ? 'ok' : 'warn'}>{c.status}</Badge>
              </div>
              <ul className="text-ink-muted">
                {c.lines.map((l) => (
                  <li key={l.item_id}>{byId.get(l.item_id)?.name}: system {l.system_qty}, counted {l.counted_qty}{l.variance !== 0 && <strong className="text-danger"> (variance {l.variance})</strong>}</li>
                ))}
              </ul>
              {c.status === 'draft' && (variances.length === 0 || canApprove
                ? <Button size="sm" onClick={() => post(c)}>Post count</Button>
                : <p className="text-warn">Variances need manager approval before they can be posted.</p>)}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
