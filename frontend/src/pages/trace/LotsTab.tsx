import { Search } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { EmptyState, Skeleton, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { fmtDate, fmtDateTime } from '@/lib/format'
import { qs, useApi } from '@/lib/useApi'
import { LotDetailModal } from '@/pages/trace/LotDetailModal'
import { STATUS_LABEL, STATUS_TONE, type Lot } from '@/pages/trace/types'

const SIZE = 15

export function LotsTab() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [soon, setSoon] = useState(false)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const { data, loading, reload } = useApi<{ total: number; items: Lot[] }>(`/lots${qs({ q: search, status, expiring_hours: soon ? 48 : '', page, size: SIZE })}`)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-52 flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-muted" aria-hidden />
          <Input aria-label="Search lots" className="pl-9" placeholder="Lot code, food or supplier lot" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        </div>
        <Select aria-label="Status" className="w-auto" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">Any status</option>
          {Object.entries(STATUS_LABEL).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={soon} onChange={(e) => { setSoon(e.target.checked); setPage(1) }} /> Use-by within 48 hours
        </label>
      </div>
      <ul className="space-y-2 md:hidden">
        {loading && !data && <li><Skeleton className="h-24 w-full" /></li>}
        {data?.items.map((l) => (
          <li key={l.id}>
            <button type="button" onClick={() => setOpen(l.id)} className="w-full space-y-1 rounded-xl border border-border bg-surface p-3 text-left active:bg-surface-muted">
              <span className="flex items-center justify-between gap-2">
                <span className="break-all font-semibold">{l.code}</span>
                <Badge tone={STATUS_TONE[l.status]}>{STATUS_LABEL[l.status]}</Badge>
              </span>
              <span className="block text-sm">{l.item}{l.pack_description ? <span className="text-ink-muted"> - {l.pack_count} x {l.pack_description}</span> : null}</span>
              <span className="flex flex-wrap items-center gap-x-3 text-xs text-ink-muted">
                <span>Use by {l.use_by ? fmtDateTime(l.use_by) : '-'}</span>
                {l.past_use_by && l.status === 'active' && <Badge tone="critical">Past</Badge>}
                <span>{l.location}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <div className="hidden md:block">
      <Table>
        <thead><tr><Th>Lot</Th><Th>Food</Th><Th>Supplier</Th><Th>Produced</Th><Th>Expiry</Th><Th>Use by</Th><Th>Status</Th><Th>Location</Th></tr></thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={8} /> : data?.items.map((l) => (
            <tr key={l.id} className="cursor-pointer" onClick={() => setOpen(l.id)}>
              <Td className="font-medium">{l.code}</Td>
              <Td>{l.item}{l.pack_description ? <span className="block text-xs text-ink-muted">{l.pack_count} x {l.pack_description}</span> : null}</Td>
              <Td>{l.supplier ?? '-'}{l.supplier_lot ? <span className="block text-xs text-ink-muted">lot {l.supplier_lot}</span> : null}</Td>
              <Td>{l.produced_on ? fmtDate(l.produced_on) : '-'}</Td>
              <Td>{l.expiry_on ? fmtDate(l.expiry_on) : '-'}</Td>
              <Td>{l.use_by ? fmtDateTime(l.use_by) : '-'}{l.past_use_by && l.status === 'active' && <Badge tone="critical" className="ml-1">Past</Badge>}</Td>
              <Td><Badge tone={STATUS_TONE[l.status]}>{STATUS_LABEL[l.status]}</Badge></Td>
              <Td>{l.location}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      </div>
      {data?.items.length === 0 && <EmptyState title="No lots found" hint="Lots appear when food is received. Try clearing the search or the filters." />}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}
      {open !== null && <LotDetailModal key={open} initialId={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  )
}
