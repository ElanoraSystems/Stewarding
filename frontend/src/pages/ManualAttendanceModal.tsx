import { useState, type FormEvent } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { iso } from '@/lib/dates'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

export function ManualAttendanceModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const run = useRun()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [employeeId, setEmployeeId] = useState('')
  const [day, setDay] = useState(() => iso(new Date(Date.now() - 86400000)))
  const [checkIn, setCheckIn] = useState('06:00')
  const [checkOut, setCheckOut] = useState('14:00')
  const [reason, setReason] = useState('')
  const employees = useApi<{ items: { id: number; full_name: string }[] }>(locationId ? `/employees${qs({ location_id: locationId, status: 'active', size: 200 })}` : null)

  async function save(event: FormEvent) {
    event.preventDefault()
    const body = { employee_id: Number(employeeId), location_id: locationId, day, check_in_time: `${checkIn}:00`, check_out_time: `${checkOut}:00`, reason }
    if (await run(() => api('/attendance/manual', { body }), 'Attendance added')) onSaved()
  }

  return (
    <Modal open title="Add missing attendance" onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        <p className="rounded-md bg-surface-muted px-3 py-2 text-sm text-ink-muted">
          Use this when an employee worked but did not punch in or out. The day counts as present, with late time worked out from the shift.
          If they punched in but forgot to punch out, use Correct on their record instead.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Location"><LocationSelect className="w-full" value={locationId} onChange={(id) => { setLocationId(id); setEmployeeId('') }} /></Field>
          <Field label="Employee" hint={employees.data?.items.length === 0 ? 'Nobody is assigned to this location yet. Assign employees to it under Employees, or pick another location.' : undefined}>
            <Select required value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              <option value="">{employees.data?.items.length === 0 ? 'No employees at this location' : 'Select'}</option>
              {employees.data?.items.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
            </Select>
          </Field>
          <Field label="Date"><Input required type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
          <span />
          <Field label="Punch in"><Input required type="time" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} /></Field>
          <Field label="Punch out" hint="An earlier time than punch in means the next morning."><Input required type="time" value={checkOut} onChange={(e) => setCheckOut(e.target.value)} /></Field>
        </div>
        <Field label="Reason" hint="Kept in the record and shown to the employee."><Input required minLength={5} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!employeeId || !locationId}>Add attendance</Button>
        </div>
      </form>
    </Modal>
  )
}
