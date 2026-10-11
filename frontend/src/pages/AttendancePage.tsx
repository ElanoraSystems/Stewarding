import { useState, type FormEvent } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtTime, hoursMinutes } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { AbsencePanel } from '@/pages/AbsencePanel'
import { ManualAttendanceModal } from '@/pages/ManualAttendanceModal'
import { MyShiftCard } from '@/pages/MyShiftCard'

interface Record {
  id: number
  employee_name?: string
  location_id: number
  local_date: string
  check_in_at: string
  check_out_at: string | null
  late_minutes: number
  payable_minutes: number | null
  overtime_minutes: number | null
  exception_reason: string | null
  open: boolean
  missed_checkout: boolean
}

interface Listing {
  total: number
  items: Record[]
}

const SIZE = 15

export function AttendancePage() {
  const { me } = useAuth()
  const run = useRun()
  const canView = me?.permissions.includes('attendance.view') ?? false
  const canCorrect = me?.permissions.includes('attendance.correct') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [correcting, setCorrecting] = useState<Record | null>(null)
  const [field, setField] = useState('check_out_at')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [adding, setAdding] = useState(false)

  const path = canView
    ? `/attendance${qs({ location_id: locationId, date_from: from, date_to: to, page, size: SIZE })}`
    : `/attendance/mine${qs({ page, size: SIZE })}`
  const { data, loading, reload } = useApi<Listing>(path)
  const locationNames = new Map(me?.locations.map((l) => [l.id, l.name]))

  async function submitCorrection(event: FormEvent) {
    event.preventDefault()
    if (!correcting) return
    const ok = await run(
      () => api(`/attendance/${correcting.id}/correct`, { body: { field, new_value: new Date(value).toISOString(), reason } }),
      'Attendance corrected',
    )
    if (ok) {
      setCorrecting(null)
      setReason('')
      reload()
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Attendance</h1>
      <MyShiftCard onChange={reload} />
      {me?.permissions.includes('attendance.absence') && <AbsencePanel />}

      <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
        <h2 className="text-lg font-semibold">{canView ? 'Attendance records' : 'My attendance history'}</h2>
        {canCorrect && <Button size="sm" onClick={() => setAdding(true)}>Add missing attendance</Button>}
      </div>
      {canView && (
        <div className="flex flex-wrap gap-3">
          <LocationSelect allowAll value={locationId} onChange={(id) => { setLocationId(id); setPage(1) }} />
          <Input aria-label="From date" type="date" className="w-auto" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1) }} />
          <Input aria-label="To date" type="date" className="w-auto" value={to} onChange={(e) => { setTo(e.target.value); setPage(1) }} />
        </div>
      )}
      <Table>
        <thead>
          <tr>
            <Th>Date</Th>
            {canView && <Th>Employee</Th>}
            <Th>Location</Th>
            <Th>In</Th>
            <Th>Out</Th>
            <Th>Worked</Th>
            <Th>Overtime</Th>
            <Th>Flags</Th>
            {canCorrect && <Th />}
          </tr>
        </thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={8} /> : data?.items.map((r) => (
            <tr key={r.id}>
              <Td>{fmtDate(r.local_date)}</Td>
              {canView && <Td className="font-medium">{r.employee_name}</Td>}
              <Td>{locationNames.get(r.location_id)}</Td>
              <Td>{fmtTime(r.check_in_at)}</Td>
              <Td>{r.open ? 'On duty' : fmtTime(r.check_out_at)}</Td>
              <Td>{hoursMinutes(r.payable_minutes)}</Td>
              <Td>{hoursMinutes(r.overtime_minutes)}</Td>
              <Td className="space-x-1">
                {r.late_minutes > 0 && <Badge tone="warn">Late {r.late_minutes}m</Badge>}
                {r.missed_checkout && <Badge tone="critical">Missed checkout</Badge>}
                {r.exception_reason?.startsWith('Manual entry') ? <Badge title={r.exception_reason}>Manual entry</Badge>
                  : r.exception_reason && <Badge tone="warn" title={r.exception_reason}>Exception</Badge>}
              </Td>
              {canCorrect && <Td><Button size="sm" variant="outline" onClick={() => { setCorrecting(r); setValue('') }}>Correct</Button></Td>}
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.items.length === 0 && <EmptyState title="No attendance records" hint="Records appear after the first check-in." />}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}

      {adding && <ManualAttendanceModal onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload() }} />}

      <Modal open={correcting !== null} title="Correct attendance" onClose={() => setCorrecting(null)}>
        <form onSubmit={submitCorrection} className="space-y-3">
          <p className="text-sm text-ink-muted">The original value stays in the record history and the change is audited.</p>
          <Field label="Field">
            <Select value={field} onChange={(e) => setField(e.target.value)}>
              <option value="check_in_at">Check-in time</option>
              <option value="check_out_at">Check-out time</option>
            </Select>
          </Field>
          <Field label="New time (your local time)"><Input required type="datetime-local" value={value} onChange={(e) => setValue(e.target.value)} /></Field>
          <Field label="Reason"><Input required minLength={5} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setCorrecting(null)}>Cancel</Button>
            <Button type="submit">Apply correction</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
