import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { fmtDateTime } from '@/lib/format'
import { qs, useApi } from '@/lib/useApi'

interface Entry {
  id: number
  created_at: string
  user: string | null
  action: string
  entity: string
  entity_id: number | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}

const SIZE = 20

export function AuditPage() {
  const [action, setAction] = useState('')
  const [entity, setEntity] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const { data, loading } = useApi<{ total: number; items: Entry[] }>(
    `/audit${qs({ action, entity, date_from: from, date_to: to, page, size: SIZE })}`,
  )
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1) }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Audit Logs</h1>
      <div className="filter-bar">
        <Input aria-label="Action starts with" className="w-48" placeholder="Action, e.g. employee" value={action} onChange={(e) => reset(setAction)(e.target.value)} />
        <Input aria-label="Entity" className="w-44" placeholder="Entity, e.g. location" value={entity} onChange={(e) => reset(setEntity)(e.target.value)} />
        <Input aria-label="From date" type="date" className="w-auto" value={from} onChange={(e) => reset(setFrom)(e.target.value)} />
        <Input aria-label="To date" type="date" className="w-auto" value={to} onChange={(e) => reset(setTo)(e.target.value)} />
      </div>
      <Table>
        <thead><tr><Th>Time</Th><Th>User</Th><Th>Action</Th><Th>Record</Th><Th>Changes</Th></tr></thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={5} /> : data?.items.map((e) => (
            <tr key={e.id}>
              <Td className="whitespace-nowrap">{fmtDateTime(e.created_at)}</Td>
              <Td>{e.user ?? 'System'}</Td>
              <Td className="font-medium">{e.action}</Td>
              <Td>{e.entity}{e.entity_id ? ` #${e.entity_id}` : ''}</Td>
              <Td>
                {(e.before || e.after) ? (
                  <details>
                    <summary className="cursor-pointer text-brand">View</summary>
                    <pre className="mt-1 max-w-md overflow-x-auto rounded bg-surface-muted p-2 text-xs">{JSON.stringify({ before: e.before, after: e.after }, null, 2)}</pre>
                  </details>
                ) : '-'}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.items.length === 0 && <EmptyState title="No audit entries match" />}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}
    </div>
  )
}
