import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { todayIso, weekRange } from '@/lib/format'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { ChecklistConfig } from '@/pages/ChecklistConfig'
import { ChecklistTaskCard, type Instance } from '@/pages/ChecklistTaskCard'
import type { EmployeeRow } from '@/pages/EmployeeForm'

const DONE = ['completed', 'pending_verification', 'verified', 'waived']

export function ChecklistsPage({ frequency }: { frequency: 'daily' | 'weekly' }) {
  const { me } = useAuth()
  const run = useRun()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [day, setDay] = useState(todayIso())
  const [status, setStatus] = useState('')
  const [configuring, setConfiguring] = useState(false)
  const canConfigure = me?.permissions.includes('checklist.configure') ?? false
  const weekly = frequency === 'weekly'
  const range = weekRange(day)

  const { data, loading, reload } = useApi<{ items: Instance[] }>(
    locationId === null ? null : `/checklists/instances${qs({
      location_id: locationId, status,
      ...(weekly ? { date_from: range.from, date_to: range.to, frequency: 'weekly' } : { day }), size: 200,
    })}`,
  )
  const staff = useApi<{ items: EmployeeRow[] }>(me?.permissions.includes('employee.view') ? '/employees?size=200&status=active' : null)
  const items = (data?.items ?? []).filter((i) => (weekly ? true : i.frequency !== 'weekly'))
  const done = items.filter((i) => DONE.includes(i.effective_status)).length
  const percent = items.length ? Math.round((done / items.length) * 100) : 0
  const timezone = me?.locations.find((l) => l.id === locationId)?.timezone
  const approvable = me?.permissions.includes('checklist.verify') ? items.filter((i) => i.effective_status === 'pending_verification' && i.completed_by !== me.id) : []

  async function approveAll() {
    const ids = approvable.map((i) => i.id)
    const result = await run(() => api('/checklists/instances/verify-many', { body: { instance_ids: ids } }), `${ids.length} task${ids.length === 1 ? '' : 's'} approved`)
    if (result) reload()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{weekly ? 'Weekly' : 'Daily'} Checklists</h1>
        {canConfigure && <Button variant="outline" onClick={() => setConfiguring((c) => !c)}>{configuring ? 'Back to tasks' : 'Configure'}</Button>}
      </div>

      {configuring ? <ChecklistConfig locationId={locationId} onLocation={setLocationId} /> : (
        <>
          <div className="flex flex-wrap gap-3">
            <LocationSelect value={locationId} onChange={setLocationId} />
            <Input aria-label="Date" type="date" className="w-auto" value={day} onChange={(e) => setDay(e.target.value)} />
            <Select aria-label="Status filter" className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="not_started">Not started</option>
              <option value="in_progress">In progress</option>
              <option value="pending_verification">Pending verification</option>
              <option value="completed">Completed</option>
              <option value="verified">Verified</option>
              <option value="failed">Failed</option>
              <option value="overdue">Overdue</option>
              <option value="waived">Waived</option>
            </Select>
          </div>

          <div aria-label="Completion progress">
            <div className="mb-1 flex justify-between text-sm"><span>{done} of {items.length} done</span><span>{percent}%</span></div>
            <div className="h-2 overflow-hidden rounded bg-border"><div className="h-full bg-brand" style={{ width: `${percent}%` }} /></div>
          </div>

          {approvable.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm">
              <span>{approvable.length} task{approvable.length === 1 ? '' : 's'} awaiting your approval</span>
              <Button size="sm" onClick={approveAll}>Approve all ({approvable.length})</Button>
            </div>
          )}
          {loading && !data ? <Skeleton className="h-32 w-full" /> : items.length === 0 ? (
            <EmptyState title="No tasks for this selection" hint="Tasks are generated automatically from the location's checklist templates." />
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {items.map((i) => <ChecklistTaskCard key={i.id} item={i} timezone={timezone} staff={staff.data?.items ?? []} onChanged={reload} />)}
            </div>
          )}
        </>
      )}
    </div>
  )
}
