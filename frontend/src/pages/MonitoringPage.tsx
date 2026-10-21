import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Modal } from '@/components/ui/modal'
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

interface Pending {
  start_reading_id: number
  equipment_id: number
  equipment: string
  item: string | null
  started_at: string
  minutes_open: number
}

const RANK = { overdue: 3, due: 2, upcoming: 1, done: 0 } as const
const TONE = { done: 'ok', due: 'warn', overdue: 'critical', upcoming: 'neutral' } as const

export function MonitoringPage() {
  const { me } = useAuth()
  const [locationId, setLocationId] = useState<number | null>(null)
  const [prefill, setPrefill] = useState<Prefill | null>(null)
  const [recording, setRecording] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const canRecord = me?.permissions.includes('temp.record') ?? false
  const timezone = me?.locations.find((l) => l.id === locationId)?.timezone

  const equipment = useApi<EquipmentItem[]>(locationId ? `/monitoring/equipment${qs({ location_id: locationId, k: refreshKey })}` : null)
  const due = useApi<Due[]>(locationId ? `/monitoring/due${qs({ location_id: locationId, k: refreshKey })}` : null)
  const pending = useApi<Pending[]>(locationId ? `/monitoring/pending${qs({ location_id: locationId, k: refreshKey })}` : null)
  const items = equipment.data ?? []
  const overdue = (due.data ?? []).filter((d) => d.status === 'overdue')
  const refresh = () => setRefreshKey((k) => k + 1)
  const startRecording = (next: Prefill | null) => {
    setPrefill(next)
    setRecording(true)
  }
  const stopRecording = () => {
    setPrefill(null)
    setRecording(false)
  }

  // a check is recorded when its latest slot that has started is done
  const doneSchedules = (() => {
    const latest = new Map<number, Due>()
    for (const d of due.data ?? []) {
      if (d.status === 'upcoming') continue
      const seen = latest.get(d.schedule_id)
      if (!seen || d.slot_at > seen.slot_at) latest.set(d.schedule_id, d)
    }
    return new Set([...latest.values()].filter((d) => d.status === 'done').map((d) => d.schedule_id))
  })()

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

  function timeOut(p: Pending) {
    const finish = items.find((e) => e.id === p.equipment_id)?.schedules.find((s) => s.active && s.phase === 'finish')
    if (finish) startRecording({ equipmentId: p.equipment_id, scheduleId: finish.id, startReadingId: p.start_reading_id, item: p.item })
  }

  function retest(equipmentId: number, readingId: number, stage: string) {
    const schedule = items.find((e) => e.id === equipmentId)?.schedules.find((s) => s.stage === stage)
    if (schedule) startRecording({ equipmentId, scheduleId: schedule.id, retestOf: readingId })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Monitoring</h1>
        <div className="flex flex-wrap items-center gap-3">
          {canRecord && <Button variant="outline" onClick={() => startRecording(null)}>Record another check</Button>}
          <LocationSelect value={locationId} onChange={setLocationId} />
        </div>
      </div>

      {overdue.length > 0 && (
        <div role="alert" className="flex items-center gap-2 rounded-xl border border-danger/20 border-l-4 border-l-danger bg-danger-soft px-4 py-3 text-sm font-medium text-danger">
          <AlertTriangle className="h-4 w-4" aria-hidden /> {overdue.length} check(s) overdue
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Checks due today</CardTitle></CardHeader>
        <CardContent>
          {(due.data ?? []).length === 0 ? <EmptyState title="No scheduled checks here" hint="Forms without a schedule are filled in from Record a check below." /> : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {cards.map(([key, { first: d, stages, status }]) => (
                <li key={key}>
                  <button type="button" disabled={!canRecord || status === 'done'}
                    onClick={() => startRecording({ equipmentId: d.equipment_id, scheduleId: d.schedule_id })}
                    className="flex w-full items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-left text-sm enabled:hover:bg-surface-muted">
                    <span><span className="block font-medium">{d.equipment}</span><span className="text-ink-muted">{stages.map(label).join(' and ')} at {fmtTime(d.slot_at, timezone)}</span></span>
                    <Badge tone={TONE[status]}>{label(status)}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {canRecord && <p className="mt-2 text-xs text-ink-muted">Select a check to record it.</p>}
        </CardContent>
      </Card>

      {(pending.data ?? []).length > 0 && (
        <Card>
          <CardHeader><CardTitle>Waiting for time out</CardTitle></CardHeader>
          <CardContent>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {pending.data!.map((p) => (
                <li key={p.start_reading_id}>
                  <button type="button" disabled={!canRecord} onClick={() => timeOut(p)}
                    className="flex w-full items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-left text-sm enabled:hover:bg-surface-muted">
                    <span><span className="block font-medium">{p.item ?? p.equipment}</span><span className="text-ink-muted">{p.equipment}, in at {fmtTime(p.started_at, timezone)}, {Math.floor(p.minutes_open / 60)} h {p.minutes_open % 60} min ago</span></span>
                    <Badge tone="warn">Pending</Badge>
                  </button>
                </li>
              ))}
            </ul>
            {canRecord && <p className="mt-2 text-xs text-ink-muted">Select an entry to record its time out.</p>}
          </CardContent>
        </Card>
      )}

      <Modal open={canRecord && recording} title={prefill?.retestOf ? 'Record a retest' : prefill?.startReadingId ? 'Record the time out' : 'Record a check'} onClose={stopRecording}>
        <MonitoringRecordForm equipment={items} prefill={prefill} doneSchedules={doneSchedules} onSaved={() => { refresh(); stopRecording() }} onClearRetest={stopRecording} />
      </Modal>

      <CorrectiveActionsPanel locationId={locationId} equipment={items} refreshKey={refreshKey} onRetest={retest} onChanged={refresh} />

      <h2 className="pt-2 text-lg font-semibold">Monitoring log</h2>
      <MonitoringLog locationId={locationId} equipment={items} refreshKey={refreshKey} />
    </div>
  )
}
