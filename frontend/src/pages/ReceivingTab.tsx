import { Check, Plus, Trash2 } from 'lucide-react'
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
import { useLineEntry } from '@/lib/useLineEntry'

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
  subtotal: number | null
  line_discount_total: number | null
  discount_type: DiscountType | null
  discount_value: number | null
  discount_amount: number | null
  total_discount: number | null
  total: number | null
  void_reason: string | null
  lines?: { item_id: number; code: string; name: string; qty: number; unit_cost: number | null; gross: number | null; discount_amount: number | null; line_total: number | null }[]
}

type DiscountType = 'amount' | 'percent'

interface Line {
  item: string
  qty: string
  cost: string
  discType: DiscountType
  disc: string
}

const BLANK_LINE: Line = { item: '', qty: '', cost: '', discType: 'amount', disc: '' }

const money = (n: number) => n.toFixed(2)
const cut = (type: DiscountType, value: string, base: number) => Math.min(base, type === 'percent' ? (base * Number(value || 0)) / 100 : Number(value || 0))
const lineGross = (l: Line) => Number(l.qty || 0) * Number(l.cost || 0)
const lineComplete = (l: Line) => l.item !== '' && Number(l.qty) > 0

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
  const [docDiscType, setDocDiscType] = useState<DiscountType>('amount')
  const [docDisc, setDocDisc] = useState('')
  const entry = useLineEntry<Line>(BLANK_LINE, lineComplete)
  const { attachList } = entry
  const [detail, setDetail] = useState<Doc | null>(null)
  const [voiding, setVoiding] = useState(false)
  const [voidReason, setVoidReason] = useState('')

  const pickItem = (i: number, id: string) => {
    const cost = items.find((x) => String(x.id) === id)?.unit_cost
    entry.update(i, { item: id, cost: cost != null ? String(cost) : '' })
  }
  const filled = entry.rows.filter(lineComplete)
  const subtotal = filled.reduce((sum, l) => sum + lineGross(l), 0)
  const lineDiscounts = filled.reduce((sum, l) => sum + cut(l.discType, l.disc, lineGross(l)), 0)
  const docDiscount = cut(docDiscType, docDisc, subtotal - lineDiscounts)
  const total = subtotal - lineDiscounts - docDiscount
  const hasCosts = filled.some((l) => l.cost !== '')

  async function post() {
    const ok = await run(() => api('/receipts', { body: {
      doc_type: docType, supplier_id: Number(supplierId), location_id: locationId, invoice_number: invoice,
      invoice_date: invoiceDate || null, note: note || null, update_costs: updateCosts && docType === 'receipt',
      discount_type: docDisc ? docDiscType : null, discount: docDisc ? Number(docDisc) : null,
      lines: filled.map((l) => ({
        item_id: Number(l.item), qty: Number(l.qty), unit_cost: l.cost === '' ? null : Number(l.cost),
        discount_type: l.disc ? l.discType : null, discount: l.disc ? Number(l.disc) : null,
      })),
    } }), docType === 'receipt' ? 'Delivery received and stock updated' : 'Return posted and stock reduced')
    if (ok) {
      setInvoice('')
      setInvoiceDate('')
      setNote('')
      setUpdateCosts(false)
      setDocDisc('')
      entry.reset()
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

          <div ref={attachList} className="space-y-2">
            <div className="overflow-x-auto">
              <div className="min-w-[46rem] space-y-2">
                <div aria-hidden className="grid grid-cols-[minmax(14rem,1fr)_6rem_6rem_11rem_6rem_1.25rem_2.5rem] items-end gap-2 text-sm font-medium">
                  <span>Item</span><span>Quantity</span><span>Unit cost</span><span>Discount</span><span className="text-right">Line total</span><span /><span />
                </div>
                {entry.rows.map((line, i) => (
                  <div key={i} {...entry.rowProps(i)} className="space-y-1">
                    <div className="grid grid-cols-[minmax(14rem,1fr)_6rem_6rem_11rem_6rem_1.25rem_2.5rem] items-center gap-2">
                      <Select aria-label="Item" value={line.item} onChange={(e) => pickItem(i, e.target.value)}>
                        <option value="">Select item</option>
                        {items.map((it) => <option key={it.id} value={it.id}>{it.code} - {it.name}</option>)}
                      </Select>
                      <Input aria-label="Quantity" type="number" min={1} value={line.qty} onChange={(e) => entry.update(i, { qty: e.target.value })} />
                      <Input aria-label="Unit cost" type="number" step="0.01" min={0} value={line.cost} onChange={(e) => entry.update(i, { cost: e.target.value })} />
                      <div className="flex gap-1">
                        <Select aria-label="Discount type" className="w-[4.5rem] px-2" value={line.discType} onChange={(e) => entry.update(i, { discType: e.target.value as DiscountType })}>
                          <option value="amount">Amt</option>
                          <option value="percent">%</option>
                        </Select>
                        <Input aria-label="Discount" type="number" step="0.01" min={0} value={line.disc} onChange={(e) => entry.update(i, { disc: e.target.value })} />
                      </div>
                      <output aria-label="Line total" className="flex h-10 items-center justify-end text-sm font-medium tabular-nums">
                        {line.cost !== '' && lineComplete(line) ? money(lineGross(line) - cut(line.discType, line.disc, lineGross(line))) : '-'}
                      </output>
                      <span className="flex h-10 items-center text-ok" aria-label={line.committed ? 'Line saved' : undefined}>{line.committed && <Check className="h-4 w-4" aria-hidden />}</span>
                      {entry.rows.length > 1 ? <Button variant="ghost" size="icon" aria-label="Remove line" onClick={() => entry.remove(i)}><Trash2 className="h-4 w-4" /></Button> : <span />}
                    </div>
                    {entry.incomplete === i && <p role="alert" className="text-xs text-danger">Choose an item and a quantity, then press Enter.</p>}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" size="sm" onClick={entry.addRow}><Plus className="h-4 w-4" /> Add line</Button>
            </div>
          </div>

          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-3">
              {docType === 'receipt' && (
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={updateCosts} onChange={(e) => setUpdateCosts(e.target.checked)} /> Update item costs to these prices</label>
              )}
              <Field label="Invoice discount">
                <div className="flex gap-1">
                  <Select aria-label="Invoice discount type" className="w-24" value={docDiscType} onChange={(e) => setDocDiscType(e.target.value as DiscountType)}>
                    <option value="amount">Amount</option>
                    <option value="percent">Percent</option>
                  </Select>
                  <Input aria-label="Invoice discount" type="number" step="0.01" min={0} className="w-28" value={docDisc} onChange={(e) => setDocDisc(e.target.value)} />
                </div>
              </Field>
            </div>
            {hasCosts ? (
              <dl className="grid min-w-60 grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm" aria-label="Totals">
                <dt>Sub total</dt><dd className="text-right tabular-nums">{money(subtotal)}</dd>
                <dt>Line discounts</dt><dd className="text-right tabular-nums">-{money(lineDiscounts)}</dd>
                <dt>Invoice discount</dt><dd className="text-right tabular-nums">-{money(docDiscount)}</dd>
                <dt>Total discount</dt><dd className="text-right tabular-nums">-{money(lineDiscounts + docDiscount)}</dd>
                <dt className="border-t border-border pt-1 font-semibold">Total</dt><dd className="border-t border-border pt-1 text-right font-semibold tabular-nums">{money(total)}</dd>
              </dl>
            ) : <span className="text-sm text-ink-muted">No costs entered</span>}
          </div>
          <Button disabled={!supplierId || !locationId || !invoice.trim() || filled.length === 0 || new Set(filled.map((l) => l.item)).size !== filled.length} onClick={post}>
            {docType === 'receipt' ? 'Post receipt' : 'Post return'}
          </Button>
          {new Set(filled.map((l) => l.item)).size !== filled.length && <p className="text-sm text-danger">An item appears twice; combine the quantities into one line.</p>}
        </CardContent>
      </Card>

      <h2 className="text-lg font-semibold">Documents</h2>
      <div className="filter-bar">
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
      {list.data?.items.length === 0 && <EmptyState title="No receiving documents" />}
      {list.data && <Pagination page={page} size={SIZE} total={list.data.total} onPage={setPage} />}

      <Modal open={detail !== null} title={detail ? `${LABEL[detail.doc_type]} #${detail.id}` : ''} onClose={() => { setDetail(null); setVoiding(false) }}>
        {detail && (
          <div className="space-y-3 text-sm">
            <p><strong>{detail.supplier}</strong> - invoice {detail.invoice_number}{detail.invoice_date && ` dated ${detail.invoice_date}`}</p>
            <p className="text-ink-muted">Posted {fmtDateTime(detail.received_at)} by {detail.received_by_name} at {places.get(detail.location_id)}</p>
            {detail.note && <p>{detail.note}</p>}
            <Table>
              <thead><tr><Th>Item</Th><Th className="text-right">Qty</Th><Th className="text-right">Unit cost</Th><Th className="text-right">Discount</Th><Th className="text-right">Line total</Th></tr></thead>
              <tbody>
                {detail.lines?.map((l) => (
                  <tr key={l.item_id}><Td>{l.code} - {l.name}</Td><Td className="text-right tabular-nums">{l.qty}</Td><Td className="text-right tabular-nums">{l.unit_cost != null ? l.unit_cost.toFixed(2) : '-'}</Td><Td className="text-right tabular-nums">{l.discount_amount ? `-${l.discount_amount.toFixed(2)}` : '-'}</Td><Td className="text-right tabular-nums">{l.line_total != null ? l.line_total.toFixed(2) : '-'}</Td></tr>
                ))}
              </tbody>
            </Table>
            {detail.total != null && (
              <dl className="ml-auto grid w-60 grid-cols-[1fr_auto] gap-x-6 gap-y-1">
                <dt>Sub total</dt><dd className="text-right tabular-nums">{detail.subtotal?.toFixed(2)}</dd>
                <dt>Line discounts</dt><dd className="text-right tabular-nums">-{(detail.line_discount_total ?? 0).toFixed(2)}</dd>
                <dt>Invoice discount{detail.discount_type === 'percent' ? ` (${detail.discount_value}%)` : ''}</dt><dd className="text-right tabular-nums">-{(detail.discount_amount ?? 0).toFixed(2)}</dd>
                <dt>Total discount</dt><dd className="text-right tabular-nums">-{(detail.total_discount ?? 0).toFixed(2)}</dd>
                <dt className="border-t border-border pt-1 font-semibold">Total</dt><dd className="border-t border-border pt-1 text-right font-semibold tabular-nums">{detail.total.toFixed(2)}</dd>
              </dl>
            )}
            {detail.status === 'void' && <p className="rounded-md bg-surface-muted p-2">Voided: {detail.void_reason}</p>}
            {detail.status === 'posted' && canVoid && !voiding && <Button variant="danger" onClick={() => setVoiding(true)}>Void this document</Button>}
            {voiding && (
              <div className="space-y-2 rounded-xl border border-danger/20 border-l-4 border-l-danger bg-danger-soft p-3">
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
