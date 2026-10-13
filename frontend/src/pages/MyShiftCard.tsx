import { LogIn, LogOut } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Skeleton } from '@/components/ui/table'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtTime } from '@/lib/format'
import { currentPosition } from '@/lib/geo'
import { useRun, useToast } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface ShiftStatus {
  checked_in: boolean
  server_time: string
  employee: string
  employee_code: string
  record: { check_in_at: string; late_minutes: number } | null
  location?: { id: number; name: string; timezone: string; geofence: boolean }
  shift?: string
  incomplete_task_count: number
}

export function MyShiftCard({ onChange }: { onChange?: () => void }) {
  const run = useRun()
  const toast = useToast()
  const { data, loading, reload } = useApi<ShiftStatus>('/attendance/me/status')
  const [locationId, setLocationId] = useState<number | null>(null)
  const { me } = useAuth()
  const [exceptionOpen, setExceptionOpen] = useState(false)
  const [reason, setReason] = useState('')

  const refresh = () => {
    reload()
    onChange?.()
  }

  async function checkIn() {
    if (locationId === null) return
    const fenced = me?.locations.find((l) => l.id === locationId)?.geofence
    const ok = await run(async () => api('/attendance/check-in', { body: { location_id: locationId, ...(fenced ? await currentPosition() : {}) } }), 'Checked in')
    if (ok) refresh()
  }

  async function checkOut(withReason?: string) {
    try {
      const where = data?.location?.geofence ? await currentPosition() : {}
      await api('/attendance/check-out', { body: { exception_reason: withReason ?? null, ...where } })
      toast('ok', 'Checked out')
      setExceptionOpen(false)
      setReason('')
      refresh()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && typeof err.detail === 'object') setExceptionOpen(true)
      else toast('error', err instanceof Error ? err.message : 'Check-out failed')
    }
  }

  if (loading && !data) return <Skeleton className="h-40 w-full" />
  if (!data) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {data.employee} <span className="text-sm font-normal text-ink-muted">{data.employee_code}</span>
          <Badge tone={data.checked_in ? 'ok' : 'neutral'}>{data.checked_in ? 'On duty' : 'Not checked in'}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.checked_in && data.record && data.location ? (
          <>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div><dt className="text-ink-muted">Location</dt><dd className="font-medium">{data.location.name}</dd></div>
              <div><dt className="text-ink-muted">Shift</dt><dd className="font-medium">{data.shift ?? 'Unscheduled'}</dd></div>
              <div><dt className="text-ink-muted">Checked in</dt><dd className="font-medium">{fmtTime(data.record.check_in_at, data.location.timezone)}</dd></div>
              <div><dt className="text-ink-muted">Open tasks</dt><dd className="font-medium">{data.incomplete_task_count}</dd></div>
            </dl>
            {data.record.late_minutes > 0 && <Badge tone="warn">Checked in {data.record.late_minutes} min late</Badge>}
            <Button className="w-full sm:w-auto" onClick={() => checkOut()}>
              <LogOut className="h-4 w-4" /> Check out
            </Button>
          </>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Work location"><LocationSelect className="w-full min-w-44" value={locationId} onChange={setLocationId} /></Field>
            <Button className="w-full sm:w-auto" disabled={locationId === null} onClick={checkIn}>
              <LogIn className="h-4 w-4" /> Check in
            </Button>
          </div>
        )}
      </CardContent>

      <Modal open={exceptionOpen} title="Tasks still open" onClose={() => setExceptionOpen(false)}>
        <p className="mb-3 text-sm text-ink-muted">
          You have {data.incomplete_task_count} mandatory task(s) not finished. Finish them, or give a reason to check out anyway. The reason is recorded.
        </p>
        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setExceptionOpen(false)}>Go back</Button>
          <Button variant="danger" disabled={reason.trim().length < 5} onClick={() => checkOut(reason)}>Check out with reason</Button>
        </div>
      </Modal>
    </Card>
  )
}
