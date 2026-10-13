import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime, label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { EquipmentItem } from '@/pages/MonitoringRecordForm'

interface Reading {
  id: number
  equipment_id: number
  recorded_at: string
  stage: string
  source: string
  display: string
  parameter: string
  reference: string | null
  min_limit: number | null
  max_limit: number | null
  passed: boolean
  recorded_by: number
  recorded_by_name: string | null
  retest_of_id: number | null
  reviewed_at: string | null
  reviewed_by_name: string | null
  rejected_at: string | null
  rejected_by_name: string | null
  reject_reason: string | null
  corrective_action: { status: string } | null
}

const SIZE = 15

interface LogProps {
  locationId: number | null
  equipment: EquipmentItem[]
  refreshKey: number
}

export function MonitoringLog({ locationId, equipment, refreshKey }: LogProps) {
  const { me } = useAuth()
  const run = useRun()
  const canReview = me?.permissions.includes('temp.review') ?? false
  const [equipmentId, setEquipmentId] = useState('')
  const [result, setResult] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number[]>([])
  const [rejecting, setRejecting] = useState<number[] | null>(null)
  const [reason, setReason] = useState('')
  const timezone = me?.locations.find((l) => l.id === locationId)?.timezone
  const names = new Map(equipment.map((e) => [e.id, e.name]))

  const { data, loading, reload } = useApi<{ total: number; items: Reading[] }>(
    `/monitoring/readings${qs({ location_id: locationId, equipment_id: equipmentId, passed: result, date_from: from, date_to: to, page, size: SIZE, k: refreshKey })}`,
  )

  const pending = (data?.items ?? []).filter((r) => !r.reviewed_at && !r.rejected_at && r.recorded_by !== me?.id)
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  async function approveSelected() {
    if (await run(() => api('/monitoring/readings/review', { body: { reading_ids: selected } }), 'Approved')) {
      setSelected([])
      reload()
    }
  }

  async function reject() {
    if (rejecting && await run(() => api('/monitoring/readings/reject', { body: { reading_ids: rejecting, reason: reason.trim() } }), `${rejecting.length} reading${rejecting.length === 1 ? '' : 's'} rejected`)) {
      setRejecting(null)
      setReason('')
      setSelected([])
      reload()
    }
  }

  async function review(id: number) {
    if (await run(() => api(`/monitoring/readings/${id}/review`, { method: 'POST' }), 'Check reviewed')) reload()
  }

  return (
    <div className="space-y-3">
      <div className="filter-bar">
        <Select aria-label="Monitoring point" className="w-auto" value={equipmentId} onChange={(e) => { setEquipmentId(e.target.value); setPage(1) }}>
          <option value="">All monitoring points</option>
          {equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </Select>
        <Select aria-label="Result" className="w-auto" value={result} onChange={(e) => { setResult(e.target.value); setPage(1) }}>
          <option value="">Pass and fail</option>
          <option value="true">Passed</option>
          <option value="false">Failed</option>
        </Select>
        <Input aria-label="From date" type="date" className="w-auto" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1) }} />
        <Input aria-label="To date" type="date" className="w-auto" value={to} onChange={(e) => { setTo(e.target.value); setPage(1) }} />
      </div>
      {canReview && pending.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm">
          <span>{pending.length} on this page awaiting approval</span>
          <Button size="sm" variant="outline" onClick={() => setSelected(pending.map((r) => r.id))}>Select all</Button>
          <Button size="sm" disabled={selected.length === 0} onClick={approveSelected}>Approve selected ({selected.length})</Button>
          <Button size="sm" variant="outline" disabled={selected.length === 0} onClick={() => setRejecting(selected)}>Reject selected</Button>
        </div>
      )}
      <Table>
        <thead>
          <tr>{canReview && <Th />}<Th>Time</Th><Th>Monitoring point</Th><Th>Check</Th><Th>Value</Th><Th>Reference</Th><Th>Limits</Th><Th>Result</Th><Th>By</Th><Th>Approval</Th></tr>
        </thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={10} /> : data?.items.map((r) => (
            <tr key={r.id} className={r.passed ? undefined : 'bg-danger-soft/50'}>
              {canReview && (
                <Td>{!r.reviewed_at && !r.rejected_at && r.recorded_by !== me?.id && <input type="checkbox" aria-label={`Select reading ${r.id}`} checked={selected.includes(r.id)} onChange={() => toggle(r.id)} />}</Td>
              )}
              <Td>{fmtDateTime(r.recorded_at, timezone)}</Td>
              <Td className="font-medium">{names.get(r.equipment_id)}</Td>
              <Td>{label(r.stage)}{r.retest_of_id && <Badge className="ml-1">Retest</Badge>}</Td>
              <Td>{r.display}</Td>
              <Td>{r.reference ?? '-'}</Td>
              <Td>{r.display === 'Yes' || r.display === 'No' ? 'Must be Yes' : `${r.min_limit ?? '-'} to ${r.max_limit ?? '-'}`}</Td>
              <Td>
                <Badge tone={r.passed ? 'ok' : 'critical'}>{r.passed ? 'Pass' : 'Fail'}</Badge>
                {r.corrective_action && <span className="ml-1"><StatusBadge status={r.corrective_action.status} /></span>}
              </Td>
              <Td>{r.recorded_by_name}</Td>
              <Td>
                {r.reviewed_at ? <Badge tone="ok">Approved by {r.reviewed_by_name}</Badge>
                  : r.rejected_at ? <span><Badge tone="critical">Rejected by {r.rejected_by_name}</Badge><span className="mt-1 block text-xs text-ink-muted">{r.reject_reason}</span></span>
                  : canReview && r.recorded_by !== me?.id ? (
                    <span className="flex gap-1">
                      <Button size="sm" variant="outline" onClick={() => review(r.id)}>Approve</Button>
                      <Button size="sm" variant="ghost" className="text-danger" onClick={() => setRejecting([r.id])}>Reject</Button>
                    </span>
                  ) : <Badge title={r.recorded_by === me?.id ? 'You recorded this, so someone else approves it' : 'Waiting for a supervisor or manager'}>Awaiting approval</Badge>}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.items.length === 0 && <EmptyState title="No checks recorded for this selection" />}
      <Modal open={rejecting !== null} title={`Reject ${rejecting?.length ?? 0} reading${rejecting?.length === 1 ? '' : 's'}`} onClose={() => setRejecting(null)}>
        <p className="mb-3 text-sm text-ink-muted">The person who recorded it is told to record the check again, and the check shows as due until they do.</p>
        <Field label="Reason"><Input value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setRejecting(null)}>Cancel</Button>
          <Button variant="danger" disabled={reason.trim().length < 5} onClick={reject}>Reject</Button>
        </div>
      </Modal>
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}
    </div>
  )
}
