import { Printer } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { WorkLocationSelect } from '@/components/WorkLocationSelect'
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
import { useAllItems } from '@/lib/useItems'

interface Count {
  id: number
  location_id: number
  counted_at: string
  status: string
  lines: { item_id: number; system_qty: number; counted_qty: number; variance: number; reason?: string | null }[]
}

interface Limit {
  item_id: number
  received: number
  system_qty: number
  invoices: number
  opening: number
  transfers_in: number
}

export function CountsTab() {
  const { me } = useAuth()
  const run = useRun()
  const canApprove = me?.permissions.includes('stock.approve') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const [entered, setEntered] = useState<Record<number, string>>({})
  const [reasons, setReasons] = useState<Record<number, string>>({})
  const { items, byId } = useAllItems()
  const counts = useApi<Count[]>(locationId ? `/stock/counts${qs({ location_id: locationId })}` : null)
  const limits = useApi<Limit[]>(locationId ? `/stock/count-limits${qs({ location_id: locationId })}` : null)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [onlyHere, setOnlyHere] = useState(true)  // an item with nothing received here cannot be counted here, so hide it by default
  const [onlyOpen, setOnlyOpen] = useState(false)  // hide what has been counted already
  const [saved, setSaved] = useState<string | null>(null)
  const loadedFor = useRef<number | null>(null)
  const limitOf = new Map((limits.data ?? []).map((l) => [l.item_id, l]))
  const receivedAt = (id: number) => limitOf.get(id)?.received ?? 0
  const systemAt = (id: number) => limitOf.get(id)?.system_qty ?? 0
  const filled = Object.entries(entered).filter(([, v]) => v !== '')
  const overLimit = filled.some(([id, v]) => Number(v) > receivedAt(Number(id)))
  const needsReason = filled.some(([id, v]) => Number(v) > systemAt(Number(id)) && Number(v) <= receivedAt(Number(id)) && (reasons[Number(id)] ?? '').trim().length < 5)

  // the count in progress is kept on the server as it is typed, so leaving the page or changing phone does not lose it
  useEffect(() => {
    loadedFor.current = null
    setEntered({})
    setReasons({})
    setSaved(null)
    if (!locationId) return
    let live = true
    api<{ entries: Record<string, { qty: string; reason: string }>; updated_at: string | null }>(`/stock/count-draft${qs({ location_id: locationId })}`)
      .then((draft) => {
        if (!live) return
        setEntered(Object.fromEntries(Object.entries(draft.entries).filter(([, e]) => e.qty !== '').map(([id, e]) => [id, e.qty])))
        setReasons(Object.fromEntries(Object.entries(draft.entries).filter(([, e]) => e.reason).map(([id, e]) => [id, e.reason])))
        if (draft.updated_at) setSaved(fmtDateTime(draft.updated_at))
      })
      .catch(() => undefined)
      .finally(() => { if (live) loadedFor.current = locationId })
    return () => { live = false }
  }, [locationId])

  useEffect(() => {
    if (!locationId || loadedFor.current !== locationId) return
    const timer = setTimeout(() => {
      const ids = new Set([...Object.keys(entered), ...Object.keys(reasons)])
      const entries = Object.fromEntries([...ids].map((id) => [id, { qty: entered[Number(id)] ?? '', reason: reasons[Number(id)] ?? '' }]))
      api('/stock/count-draft', { method: 'PUT', body: { location_id: locationId, entries } })
        .then(() => setSaved(fmtDateTime(new Date().toISOString())))
        .catch(() => undefined)
    }, 1200)
    return () => clearTimeout(timer)
  }, [entered, reasons, locationId])

  const categories = useMemo(() => [...new Set(items.map((i) => i.category))].sort(), [items])
  const shown = items.filter((i) => {
    if (category && i.category !== category) return false
    const words = search.toLowerCase().split(/\s+/).filter(Boolean)
    if (words.length && !words.every((w) => `${i.code} ${i.name}`.toLowerCase().includes(w))) return false
    if (onlyOpen && (entered[i.id] ?? '') !== '') return false
    if (onlyHere && locationId && limits.data && receivedAt(i.id) === 0 && systemAt(i.id) === 0 && (entered[i.id] ?? '') === '') return false
    return true
  })
  const sheet = () => window.open(`/count-sheet${qs({ location_id: locationId })}`, '_blank')

  async function submit() {
    const lines = filled.map(([id, v]) => ({ item_id: Number(id), counted_qty: Number(v), reason: Number(v) > systemAt(Number(id)) ? reasons[Number(id)]?.trim() : undefined }))
    const ok = await run(() => api('/stock/counts', { body: { location_id: locationId, lines } }), 'Count saved - post it to apply variances')
    if (ok) {
      setEntered({})
      setReasons({})
      setSaved(null)
      counts.reload()
      limits.reload()
    }
  }

  async function post(count: Count) {
    if (await run(() => api(`/stock/counts/${count.id}/post`, { method: 'POST' }), 'Count posted')) counts.reload()
  }

  return (
    <div className="space-y-4">
      <div className="filter-bar">
        <WorkLocationSelect value={locationId} onChange={setLocationId} />
        <Input aria-label="Search items" className="w-56" placeholder="Search code or name" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select aria-label="Category" className="w-auto" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyHere} onChange={(e) => setOnlyHere(e.target.checked)} /> Only items held here</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> Not counted yet</label>
        <Button variant="outline" size="sm" disabled={!locationId} onClick={sheet}><Printer className="h-4 w-4" /> Print count sheet</Button>
      </div>
      <Card>
        <CardHeader><CardTitle>Physical count</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Table>
            <thead><tr><Th>Item</Th><Th className="text-right">System</Th><Th className="text-right">Received to date</Th><Th>Counted</Th></tr></thead>
            <tbody>
              {shown.map((i) => (
                <tr key={i.id}>
                  <Td>{i.code} - {i.name}</Td>
                  <Td className="text-right tabular-nums">{locationId ? systemAt(i.id) : '-'}</Td>
                  <Td className="text-right tabular-nums" title={limitOf.get(i.id) ? `Invoices ${limitOf.get(i.id)!.invoices}, opening stock ${limitOf.get(i.id)!.opening}, transfers in ${limitOf.get(i.id)!.transfers_in}` : undefined}>{locationId ? receivedAt(i.id) : '-'}</Td>
                  <Td>
                    <Input aria-label={`Counted ${i.name}`} type="number" min={0} max={receivedAt(i.id)} className="w-28" value={entered[i.id] ?? ''} onChange={(e) => setEntered((v) => ({ ...v, [i.id]: e.target.value }))} />
                    {Number(entered[i.id] ?? 0) > receivedAt(i.id) && (
                      <p role="alert" className="mt-1 max-w-64 text-xs font-medium text-danger">
                        More than the {receivedAt(i.id)} received here (invoices {limitOf.get(i.id)?.invoices ?? 0}, opening stock {limitOf.get(i.id)?.opening ?? 0}, transfers in {limitOf.get(i.id)?.transfers_in ?? 0}). Something is wrong: check the count and the receipts. It cannot be saved.
                      </p>
                    )}
                    {Number(entered[i.id] ?? 0) > systemAt(i.id) && Number(entered[i.id] ?? 0) <= receivedAt(i.id) && (
                      <div className="mt-1 space-y-1">
                        <p className="max-w-64 text-xs text-warn">Higher than the {systemAt(i.id)} the system holds. Say why:</p>
                        <Input aria-label={`Reason for ${i.name}`} className="w-64" value={reasons[i.id] ?? ''} maxLength={500} onChange={(e) => setReasons((v) => ({ ...v, [i.id]: e.target.value }))} />
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p className="text-xs text-ink-muted" aria-live="polite">
            {filled.length} counted, {shown.length} of {items.length} items shown.{saved ? ` Draft saved ${saved}. It is kept for you until the count is saved.` : ' Your progress is saved as you type.'}
          </p>
          <Button disabled={!locationId || overLimit || needsReason || filled.length === 0} onClick={submit}>Save count</Button>
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
                <span className="font-medium">Count #{c.id} - {fmtDateTime(c.counted_at)}</span>
                <Badge tone={c.status === 'posted' ? 'ok' : 'warn'}>{c.status}</Badge>
              </div>
              <ul className="text-ink-muted">
                {c.lines.map((l) => (
                  <li key={l.item_id}>{byId.get(l.item_id)?.name}: system {l.system_qty}, counted {l.counted_qty}{l.variance !== 0 && <strong className="text-danger"> (variance {l.variance})</strong>}{l.reason && <span> - {l.reason}</span>}</li>
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
