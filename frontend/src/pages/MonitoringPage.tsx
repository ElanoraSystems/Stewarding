import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { fmtTime, label } from '@/lib/format'
import { cycleOf } from '@/lib/monitoring'
import { qs, useApi } from '@/lib/useApi'
import { CorrectiveActionsPanel } from '@/pages/CorrectiveActionsPanel'
import { MonitoringLog } from '@/pages/MonitoringLog'
import { MonitoringRecordForm, type EquipmentItem, type Prefill } from '@/pages/MonitoringRecordForm'

interface Due {
  equipment_id: number
  equipment: string
  schedule_id: number
  stage: string
  slot_at: string
  status: 'done' | 'due' | 'overdue' | 'upcoming'
}

const RANK = { overdue: 3, due: 2, upcoming: 1, done: 0 } as const
const TONE = { done: 'ok', due: 'warn', overdue: 'critical', upcoming: 'neutral' } as const

export function MonitoringPage() {
  const { me } = useAuth()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [prefill, setPrefill] = useState<Prefill | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const canRecord = me?.permissions.includes('temp.record') ?? false
  const timezone = me?.locations.find((l) => l.id === locationId)?.timezone

  const equipment = useApi<EquipmentItem[]>(locationId ? `/monitoring/equipment${qs({ location_id: locationId, k: refreshKey })}` : null)
  const due = useApi<Due[]>(locationId ? `/monitoring/due${qs({ location_id: locationId, k: refreshKey })}` : null)
  const items = equipment.data ?? []
  const overdue = (due.data ?? []).filter((d) => d.status === 'overdue')
  const actionable = (due.data ?? []).filter((d) => d.status !== 'upcoming' && d.status !== 'done')
  const refresh = () => setRefreshKey((k) => k + 1)

  // checks of one point due at the same time are shown, and recorded, as one card
  const cards = (() => {
    const out = new Map<string, { first: Due; stages: string[]; status: Due['status'] }>()
    for (const d of due.data ?? []) {
      const sched = items.find((e) => e.id === d.equipment_id)?.schedules.find((s) => s.id === d.schedule_id)
      const group = sched ? cycleOf(sched, items.find((e) => e.id === d.equipment_id)!.schedules).map((s) => s.id).sort().join() : String(d.schedule_id)
      const key = `${d.equipment_id}|${d.slot_at}|${group}`
      const card = out.get(key)
      if (!card) out.set(key, { first: d, stages: [d.stage], status: d.status })
      else {
        card.stages.push(d.stage)
        if (RANK[d.status] > RANK[card.status]) card.status = d.status
      }
    }
    return [...out.entries()]
  })()

  function retest(equipmentId: number, readingId: number, stage: string) {
    const schedule = items.find((e) => e.id === equipmentId)?.schedules.find((s) => s.stage === stage)
    if (schedule) setPrefill({ equipmentId, scheduleId: schedule.id, retestOf: readingId })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Monitoring</h1>
        <LocationSelect value={locationId} onChange={setLocationId} />
      </div>

      {overdue.length > 0 && (
        <div role="alert" className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm font-medium text-danger">
          <AlertTriangle className="h-4 w-4" aria-hidden /> {overdue.length} check(s) overdue
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Checks due today</CardTitle></CardHeader>
        <CardContent>
          {(due.data ?? []).length === 0 ? <EmptyState title="No checks configured here" /> : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {cards.map(([key, { first: d, stages, status }]) => (
                <li key={key}>
                  <button type="button" disabled={!canRecord || status === 'done'}
                    onClick={() => setPrefill({ equipmentId: d.equipment_id, scheduleId: d.schedule_id })}
                    className="flex w-full items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-left text-sm enabled:hover:bg-surface-muted">
                    <span><span className="block font-medium">{d.equipment}</span><span className="text-ink-muted">{stages.map(label).join(' and ')} at {fmtTime(d.slot_at, timezone)}</span></span>
                    <Badge tone={TONE[status]}>{label(status)}</Badge>
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
          <CardHeader><CardTitle>Record a check</CardTitle></CardHeader>
          <CardContent>
            <MonitoringRecordForm equipment={items} prefill={prefill} onSaved={refresh} onClearRetest={() => setPrefill(null)} />
          </CardContent>
        </Card>
      )}

      <CorrectiveActionsPanel locationId={locationId} equipment={items} refreshKey={refreshKey} onRetest={retest} onChanged={refresh} />

      <h2 className="pt-2 text-lg font-semibold">Monitoring log</h2>
      <MonitoringLog locationId={locationId} equipment={items} refreshKey={refreshKey} />
    </div>
  )
}
