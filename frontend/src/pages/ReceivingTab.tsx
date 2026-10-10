import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { useAllItems } from '@/lib/useItems'

interface Doc {
  id: number
  doc_type: 'receipt' | 'supplier_return'
  supplier: string
  location_id: number
  invoice_number: string
  invoice_date: string | null
  received_at: string
  received_by_name: string | null
  note: string | null
  status: string
  total: number | null
  void_reason: string | null
  lines?: { item_id: number; code: string; name: string; qty: number; unit_cost: number | null }[]
}

interface Line {
  item: string
  qty: string
  cost: string
}

const SIZE = 10
const LABEL = { receipt: 'Goods receipt', supplier_return: 'Return to supplier' }

export function ReceivingTab() {
  const { me } = useAuth()
  const run = useRun()
  const canVoid = me?.permissions.includes('stock.approve') ?? false
  const { items } = useAllItems()
  const suppliers = useApi<{ id: number; name: string }[]>('/suppliers')
  const [filterSupplier, setFilterSupplier] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const list = useApi<{ total: number; items: Doc[] }>(
    `/receipts${qs({ supplier_id: filterSupplier, receipt_status: filterStatus, q: search, page, size: SIZE })}`,
  )
  const places = new Map(me?.locations.map((l) => [l.id, l.name]))

  const [docType, setDocType] = useState<'receipt' | 'supplier_return'>('receipt')
  const [supplierId, setSupplierId] = useState('')
  const [locationId, setLocationId] = useState<number | null>(null)
  const [invoice, setInvoice] = useState('')
  const [invoiceDate, setInvoiceDate] = useState('')
  const [note, setNote] = useState('')
  const [updateCosts, setUpdateCosts] = useState(false)
  const [lines, setLines] = useState<Line[]>([{ item: '', qty: '', cost: '' }])
  const [detail, setDetail] = useState<Doc | null>(null)
  const [voiding, setVoiding] = useState(false)
  const [voidReason, setVoidReason] = useState('')

  const setLine = (i: number, patch: Partial<Line>) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)))
  const pickItem = (i: number, id: string) => {
    const cost = items.find((x) => String(x.id) === id)?.unit_cost
    setLine(i, { item: id, cost: cost != null ? String(cost) : '' })
  }
  const filled = lines.filter((l) => l.item && Number(l.qty) > 0)
  const total = filled.reduce((sum, l) => sum + Number(l.qty) * (l.cost === '' ? 0 : Number(l.cost)), 0)
  const hasCosts = filled.some((l) => l.cost !== '')

  async function post() {
    const ok = await run(() => api('/receipts', { body: {
      doc_type: docType, supplier_id: Number(supplierId), location_id: locationId, invoice_number: invoice,
      invoice_date: invoiceDate || null, note: note || null, update_costs: updateCosts && docType === 'receipt',
      lines: filled.map((l) => ({ item_id: Number(l.item), qty: Number(l.qty), unit_cost: l.cost === '' ? null : Number(l.cost) })),
    } }), docType === 'receipt' ? 'Delivery received and stock updated' : 'Return posted and stock reduced')
    if (ok) {
      setInvoice('')
      setInvoiceDate('')
      setNote('')
      setUpdateCosts(false)
      setLines([{ item: '', qty: '', cost: '' }])
      list.reload()
    }
  }

  async function open(doc: Doc) {
    setDetail(await api<Doc>(`/receipts/${doc.id}`))
  }

  async function voidDoc() {
    if (!detail) return
    const ok = await run(() => api(`/receipts/${detail.id}/void`, { body: { reason: voidReason } }), 'Document voided and stock reversed')
    if (ok) {
      setVoiding(false)
      setVoidReason('')
      setDetail(null)
      list.reload()
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>New receiving document</CardTitle>
          <p className="text-sm text-ink-muted">Posting adds the quantities to stock at the chosen location, recorded against the supplier invoice number. The same invoice cannot be posted twice.</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Document">
              <Select value={docType} onChange={(e) => setDocType(e.target.value as typeof docType)}>
                <option value="receipt">Goods receipt (delivery in)</option>
                <option value="supplier_return">Return to supplier (stock out)</option>
              </Select>
            </Field>
            <Field label="Supplier">
              <Select required value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
                <option value="">Select supplier</option>
                {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
            <Field label="Location"><LocationSelect className="w-full" value={locationId} onChange={setLocationId} /></Field>
            <Field label={docType === 'receipt' ? 'Invoice number' : 'Credit note number'}><Input value={invoice} onChange={(e) => setInvoice(e.target.value)} /></Field>
            <Field label="Invoice date"><Input type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} /></Field>
            <div className="sm:col-span-2 lg:col-span-3"><Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field></div>
          </div>
          {suppliers.data?.length === 0 && <p className="text-sm text-warn">No suppliers yet. A manager adds them under Settings, Suppliers.</p>}

          <div className="space-y-2">
            {lines.map((line, i) => (
              <div key={i} className="flex flex-wrap items-end gap-2">
                <div className="min-w-56 flex-1">
                  <Field label={i === 0 ? 'Item' : ''}>
                    <Select value={line.item} onChange={(e) => pickItem(i, e.target.value)}>
                      <option value="">Select item</option>
                      {items.map((it) => <option key={it.id} value={it.id}>{it.code} - {it.name}</option>)}
                    </Select>
                  </Field>
                </div>
                <Field label={i === 0 ? 'Quantity' : ''}><Input type="number" min={1} className="w-28" value={line.qty} onChange={(e) => setLine(i, { qty: e.target.value })} /></Field>
                <Field label={i === 0 ? 'Unit cost' : ''}><Input type="number" step="0.01" min={0} className="w-28" value={line.cost} onChange={(e) => setLine(i, { cost: e.target.value })} /></Field>
                {lines.length > 1 && <Button variant="ghost" size="icon" aria-label="Remove line" onClick={() => setLines((ls) => ls.filter((_, n) => n !== i))}><Trash2 className="h-4 w-4" /></Button>}
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setLines((ls) => [...ls, { item: '', qty: '', cost: '' }])}><Plus className="h-4 w-4" /> Add line</Button>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            {docType === 'receipt' ? (
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={updateCosts} onChange={(e) => setUpdateCosts(e.target.checked)} /> Update item costs to these prices</label>
            ) : <span />}
            <span className="text-sm font-medium">{hasCosts ? `Total ${total.toFixed(2)}` : 'No costs entered'}</span>
          </div>
          <Button disabled={!supplierId || !locationId || !invoice.trim() || filled.length === 0 || new Set(filled.map((l) => l.item)).size !== filled.length} onClick={post}>
            {docType === 'receipt' ? 'Post receipt' : 'Post return'}
          </Button>
          {new Set(filled.map((l) => l.item)).size !== filled.length && <p className="text-sm text-danger">An item appears twice; combine the quantities into one line.</p>}
        </CardContent>
      </Card>

      <h2 className="text-lg font-semibold">Documents</h2>
      <div className="flex flex-wrap gap-3">
        <Select aria-label="Supplier filter" className="w-auto" value={filterSupplier} onChange={(e) => { setFilterSupplier(e.target.value); setPage(1) }}>
          <option value="">All suppliers</option>
          {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
        <Select aria-label="Status filter" className="w-auto" value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setPage(1) }}>
          <option value="">Posted and void</option>
          <option value="posted">Posted</option>
          <option value="void">Void</option>
        </Select>
        <Input aria-label="Search invoices" className="w-56" placeholder="Search invoice or note" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
      </div>
      <Table>
        <thead><tr><Th>#</Th><Th>Received</Th><Th>Type</Th><Th>Supplier</Th><Th>Invoice</Th><Th>Location</Th><Th className="text-right">Total</Th><Th>Status</Th><Th /></tr></thead>
        <tbody>
          {list.loading && !list.data ? <SkeletonRows cols={9} /> : list.data?.items.map((d) => (
            <tr key={d.id}>
              <Td>{d.id}</Td>
              <Td>{fmtDateTime(d.received_at)}</Td>
              <Td><Badge tone={d.doc_type === 'receipt' ? 'ok' : 'warn'}>{LABEL[d.doc_type]}</Badge></Td>
              <Td className="font-medium">{d.supplier}</Td>
              <Td>{d.invoice_number}</Td>
              <Td>{places.get(d.location_id)}</Td>
              <Td className="text-right tabular-nums">{d.total != null ? d.total.toFixed(2) : '-'}</Td>
              <Td><StatusBadge status={d.status} /></Td>
              <Td><Button size="sm" variant="outline" onClick={() => open(d)}>View</Button></Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {list.data?.items.length === 0 && <EmptyState title="No receiving documents" hint="Post the first delivery above." />}
      {list.data && <Pagination page={page} size={SIZE} total={list.data.total} onPage={setPage} />}

      <Modal open={detail !== null} title={detail ? `${LABEL[detail.doc_type]} #${detail.id}` : ''} onClose={() => { setDetail(null); setVoiding(false) }}>
        {detail && (
          <div className="space-y-3 text-sm">
            <p><strong>{detail.supplier}</strong> - invoice {detail.invoice_number}{detail.invoice_date && ` dated ${detail.invoice_date}`}</p>
            <p className="text-ink-muted">Posted {fmtDateTime(detail.received_at)} by {detail.received_by_name} at {places.get(detail.location_id)}</p>
            {detail.note && <p>{detail.note}</p>}
            <Table>
              <thead><tr><Th>Item</Th><Th className="text-right">Qty</Th><Th className="text-right">Unit cost</Th></tr></thead>
              <tbody>
                {detail.lines?.map((l) => (
                  <tr key={l.item_id}><Td>{l.code} - {l.name}</Td><Td className="text-right tabular-nums">{l.qty}</Td><Td className="text-right tabular-nums">{l.unit_cost != null ? l.unit_cost.toFixed(2) : '-'}</Td></tr>
                ))}
              </tbody>
            </Table>
            {detail.total != null && <p className="text-right font-medium">Total {detail.total.toFixed(2)}</p>}
            {detail.status === 'void' && <p className="rounded-md bg-surface-muted p-2">Voided: {detail.void_reason}</p>}
            {detail.status === 'posted' && canVoid && !voiding && <Button variant="danger" onClick={() => setVoiding(true)}>Void this document</Button>}
            {voiding && (
              <div className="space-y-2 rounded-md border border-danger/40 bg-danger-soft p-3">
                <p className="text-danger">Voiding reverses the stock with new ledger entries. The original entries stay in the history.</p>
                <Field label="Reason"><Input value={voidReason} onChange={(e) => setVoidReason(e.target.value)} /></Field>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setVoiding(false)}>Cancel</Button>
                  <Button variant="danger" disabled={voidReason.trim().length < 5} onClick={voidDoc}>Confirm void</Button>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
