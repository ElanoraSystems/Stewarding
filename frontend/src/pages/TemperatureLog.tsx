import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime, label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import type { EquipmentItem } from '@/pages/TemperatureRecordForm'

interface Reading {
  id: number
  equipment_id: number
  recorded_at: string
  stage: string
  source: string
  temp_c: number
  min_limit: number | null
  max_limit: number | null
  passed: boolean
  recorded_by: number
  recorded_by_name: string | null
  retest_of_id: number | null
  reviewed_at: string | null
  corrective_action: { status: string } | null
}

const SIZE = 15

interface LogProps {
  locationId: number | null
  equipment: EquipmentItem[]
  refreshKey: number
}

export function TemperatureLog({ locationId, equipment, refreshKey }: LogProps) {
  const { me } = useAuth()
  const run = useRun()
  const canReview = me?.permissions.includes('temp.review') ?? false
  const [equipmentId, setEquipmentId] = useState('')
  const [result, setResult] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const timezone = me?.locations.find((l) => l.id === locationId)?.timezone
  const names = new Map(equipment.map((e) => [e.id, e.name]))

  const { data, loading, reload } = useApi<{ total: number; items: Reading[] }>(
    `/temperature/readings${qs({ location_id: locationId, equipment_id: equipmentId, passed: result, date_from: from, date_to: to, page, size: SIZE, k: refreshKey })}`,
  )

  async function review(id: number) {
    if (await run(() => api(`/temperature/readings/${id}/review`, { method: 'POST' }), 'Reading reviewed')) reload()
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        <Select aria-label="Equipment" className="w-auto" value={equipmentId} onChange={(e) => { setEquipmentId(e.target.value); setPage(1) }}>
          <option value="">All equipment</option>
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
      <Table>
        <thead>
          <tr><Th>Time</Th><Th>Equipment</Th><Th>Stage</Th><Th>Temp</Th><Th>Limits</Th><Th>Result</Th><Th>By</Th><Th>Review</Th></tr>
        </thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={8} /> : data?.items.map((r) => (
            <tr key={r.id} className={r.passed ? undefined : 'bg-danger-soft/50'}>
              <Td>{fmtDateTime(r.recorded_at, timezone)}</Td>
              <Td className="font-medium">{names.get(r.equipment_id)}</Td>
              <Td>{label(r.stage)}{r.retest_of_id && <Badge className="ml-1">Retest</Badge>}</Td>
              <Td>{r.temp_c} C</Td>
              <Td>{r.min_limit ?? '-'} to {r.max_limit ?? '-'}</Td>
              <Td>
                <Badge tone={r.passed ? 'ok' : 'critical'}>{r.passed ? 'Pass' : 'Fail'}</Badge>
                {r.corrective_action && <span className="ml-1"><StatusBadge status={r.corrective_action.status} /></span>}
              </Td>
              <Td>{r.recorded_by_name}</Td>
              <Td>
                {r.reviewed_at ? <Badge tone="ok">Reviewed</Badge>
                  : canReview && r.recorded_by !== me?.id ? <Button size="sm" variant="outline" onClick={() => review(r.id)}>Review</Button>
                  : <Badge>Pending</Badge>}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.items.length === 0 && <EmptyState title="No readings for this selection" />}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}
    </div>
  )
}
