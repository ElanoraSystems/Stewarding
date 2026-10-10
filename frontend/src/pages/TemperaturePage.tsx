import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { fmtTime, label } from '@/lib/format'
import { qs, useApi } from '@/lib/useApi'
import { CorrectiveActionsPanel } from '@/pages/CorrectiveActionsPanel'
import { TemperatureLog } from '@/pages/TemperatureLog'
import { TemperatureRecordForm, type EquipmentItem, type Prefill } from '@/pages/TemperatureRecordForm'

interface Due {
  equipment_id: number
  equipment: string
  schedule_id: number
  stage: string
  slot_at: string
  status: 'done' | 'due' | 'overdue' | 'upcoming'
}

const TONE = { done: 'ok', due: 'warn', overdue: 'critical', upcoming: 'neutral' } as const

export function TemperaturePage() {
  const { me } = useAuth()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [prefill, setPrefill] = useState<Prefill | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const canRecord = me?.permissions.includes('temp.record') ?? false
  const timezone = me?.locations.find((l) => l.id === locationId)?.timezone

  const equipment = useApi<EquipmentItem[]>(locationId ? `/temperature/equipment${qs({ location_id: locationId, k: refreshKey })}` : null)
  const due = useApi<Due[]>(locationId ? `/temperature/due${qs({ location_id: locationId, k: refreshKey })}` : null)
  const items = equipment.data ?? []
  const overdue = (due.data ?? []).filter((d) => d.status === 'overdue')
  const actionable = (due.data ?? []).filter((d) => d.status !== 'upcoming' && d.status !== 'done')
  const refresh = () => setRefreshKey((k) => k + 1)

  function retest(equipmentId: number, readingId: number, stage: string) {
    const schedule = items.find((e) => e.id === equipmentId)?.schedules.find((s) => s.stage === stage)
    if (schedule) setPrefill({ equipmentId, scheduleId: schedule.id, retestOf: readingId })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Temperature Monitoring</h1>
        <LocationSelect value={locationId} onChange={setLocationId} />
      </div>

      {overdue.length > 0 && (
        <div role="alert" className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm font-medium text-danger">
          <AlertTriangle className="h-4 w-4" aria-hidden /> {overdue.length} temperature check(s) overdue
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Checks due today</CardTitle></CardHeader>
        <CardContent>
          {(due.data ?? []).length === 0 ? <EmptyState title="No monitoring schedule configured here" /> : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(due.data ?? []).map((d) => (
                <li key={`${d.schedule_id}-${d.slot_at}`}>
                  <button type="button" disabled={!canRecord || d.status === 'done'}
                    onClick={() => setPrefill({ equipmentId: d.equipment_id, scheduleId: d.schedule_id })}
                    className="flex w-full items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-left text-sm enabled:hover:bg-surface-muted">
                    <span><span className="block font-medium">{d.equipment}</span><span className="text-ink-muted">{label(d.stage)} at {fmtTime(d.slot_at, timezone)}</span></span>
                    <Badge tone={TONE[d.status]}>{label(d.status)}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {actionable.length > 0 && canRecord && <p className="mt-2 text-xs text-ink-muted">Select a check to start recording it.</p>}
        </CardContent>
      </Card>

      {canRecord && (
        <Card>
          <CardHeader><CardTitle>Record a reading</CardTitle></CardHeader>
          <CardContent>
            <TemperatureRecordForm equipment={items} prefill={prefill} onSaved={refresh} onClearRetest={() => setPrefill(null)} />
          </CardContent>
        </Card>
      )}

      <CorrectiveActionsPanel locationId={locationId} equipment={items} refreshKey={refreshKey} onRetest={retest} onChanged={refresh} />

      <h2 className="pt-2 text-lg font-semibold">Reading log</h2>
      <TemperatureLog locationId={locationId} equipment={items} refreshKey={refreshKey} />
    </div>
  )
}
