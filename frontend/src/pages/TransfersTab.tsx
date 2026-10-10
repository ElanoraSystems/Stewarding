import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'
import { useAllItems } from '@/lib/useItems'

interface Transfer {
  id: number
  from_location_id: number
  to_location_id: number
  status: string
  requested_by: number
  requested_at: string
  note: string | null
  lines: { item_id: number; qty: number }[]
}

export function TransfersTab() {
  const { me } = useAuth()
  const run = useRun()
  const canApprove = me?.permissions.includes('stock.approve') ?? false
  const { data, reload } = useApi<Transfer[]>('/stock/transfers')
  const destinations = useApi<{ id: number; name: string }[]>('/stock/locations')
  const { items, byId } = useAllItems()
  const [from, setFrom] = useState(String(me?.locations[0]?.id ?? ''))
  const [to, setTo] = useState('')
  const [note, setNote] = useState('')
  const [lines, setLines] = useState<{ item: string; qty: string }[]>([{ item: '', qty: '' }])
  const places = new Map(destinations.data?.map((l) => [l.id, l.name]))
  const setLine = (i: number, key: 'item' | 'qty', value: string) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, [key]: value } : l)))

  async function request() {
    const ok = await run(() => api('/stock/transfers', { body: {
      from_location_id: Number(from), to_location_id: Number(to), note: note || null,
      lines: lines.filter((l) => l.item && l.qty).map((l) => ({ item_id: Number(l.item), qty: Number(l.qty) })),
    } }), canApprove ? 'Transfer completed' : 'Transfer requested - awaiting approval')
    if (ok) {
      setLines([{ item: '', qty: '' }])
      setNote('')
      reload()
    }
  }

  async function decide(id: number, approve: boolean) {
    if (await run(() => api(`/stock/transfers/${id}/decision`, { body: { approve } }), approve ? 'Transfer approved' : 'Transfer rejected')) reload()
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>New transfer</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="From"><Select value={from} onChange={(e) => setFrom(e.target.value)}>{me?.locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
            <Field label="To">
              <Select value={to} onChange={(e) => setTo(e.target.value)}>
                <option value="">Select</option>
                {destinations.data?.filter((l) => String(l.id) !== from).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </Select>
            </Field>
          </div>
          {lines.map((line, i) => (
            <div key={i} className="flex items-end gap-2">
              <Field label={i === 0 ? 'Item' : ''}>
                <Select value={line.item} onChange={(e) => setLine(i, 'item', e.target.value)}>
                  <option value="">Select item</option>
                  {items.map((it) => <option key={it.id} value={it.id}>{it.code} - {it.name}</option>)}
                </Select>
              </Field>
              <Field label={i === 0 ? 'Qty' : ''}><Input type="number" min={1} className="w-24" value={line.qty} onChange={(e) => setLine(i, 'qty', e.target.value)} /></Field>
              {lines.length > 1 && <Button variant="ghost" size="icon" aria-label="Remove line" onClick={() => setLines((ls) => ls.filter((_, n) => n !== i))}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={() => setLines((ls) => [...ls, { item: '', qty: '' }])}><Plus className="h-4 w-4" /> Add line</Button>
          <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <Button disabled={!to || !lines.some((l) => l.item && l.qty)} onClick={request}>{canApprove ? 'Transfer now' : 'Request transfer'}</Button>
        </CardContent>
      </Card>

      <h2 className="text-lg font-semibold">Transfers</h2>
      {data?.length === 0 && <EmptyState title="No transfers yet" />}
      <ul className="space-y-2">
        {data?.map((t) => (
          <li key={t.id} className="rounded-lg border border-border bg-surface p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">#{t.id}: {places.get(t.from_location_id) ?? t.from_location_id} to {places.get(t.to_location_id) ?? t.to_location_id}</span>
              <StatusBadge status={t.status} />
            </div>
            <p className="text-ink-muted">{t.lines.map((l) => `${l.qty} x ${byId.get(l.item_id)?.name ?? l.item_id}`).join(', ')} - {fmtDateTime(t.requested_at)}</p>
            {t.status === 'requested' && canApprove && t.requested_by !== me?.id && (
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={() => decide(t.id, true)}>Approve</Button>
                <Button size="sm" variant="danger" onClick={() => decide(t.id, false)}>Reject</Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
