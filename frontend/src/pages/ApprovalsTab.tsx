import { useState } from 'react'
import { DecisionDialog, type Decision } from '@/components/DecisionDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime } from '@/lib/format'
import { useToast } from '@/lib/toast'

export interface TaskWaiting { id: number; description: string; checklist: string; location_id: number; local_date: string; done_by: string; done_at: string; comment: string | null; has_photo: boolean }
export interface ReadingWaiting { id: number; equipment: string; stage: string; value: string; passed: boolean; location_id: number; done_by: string; done_at: string; comment: string | null }
export interface Waiting { tasks: TaskWaiting[]; readings: ReadingWaiting[]; count: number }

type Kind = 'tasks' | 'readings'

/** Everything entered and waiting for approval, in one place: checklist tasks done and monitoring readings recorded. */
export function ApprovalsTab({ data, loading, reload }: { data: Waiting | null; loading: boolean; reload: () => void }) {
  const { me } = useAuth()
  const toast = useToast()
  const places = new Map((me?.locations ?? []).map((l) => [l.id, l.name]))
  const [picked, setPicked] = useState<Record<Kind, number[]>>({ tasks: [], readings: [] })
  const [deciding, setDeciding] = useState<{ kind: Kind; ids: number[]; initial: Decision } | null>(null)
  const toggle = (kind: Kind, id: number) => setPicked((p) => ({ ...p, [kind]: p[kind].includes(id) ? p[kind].filter((x) => x !== id) : [...p[kind], id] }))

  async function decide(decision: Decision, note: string) {
    if (!deciding) return false
    const { kind, ids } = deciding
    try {
      if (kind === 'tasks') {
        if (decision === 'approved') await api('/checklists/instances/verify-many', { body: { instance_ids: ids, comment: note || null } })
        else for (const id of ids) await api(`/checklists/instances/${id}/verify`, { body: { approve: false, comment: note } })
      } else if (decision === 'approved') await api('/monitoring/readings/review', { body: { reading_ids: ids, comment: note || null } })
      else await api('/monitoring/readings/reject', { body: { reading_ids: ids, reason: note } })
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Could not save the decision')
      return false
    }
    toast('ok', `${ids.length} ${decision === 'approved' ? 'approved' : 'rejected'}`)
    setDeciding(null)
    setPicked((p) => ({ ...p, [kind]: [] }))
    reload()
    return true
  }

  if (loading && !data) return <Skeleton className="h-32 w-full" />
  if (!data || data.count === 0) return <EmptyState title="Nothing is waiting for your approval" />

  const section = <T extends { id: number }>(kind: Kind, title: string, rows: T[], line: (r: T) => { name: string; detail: string; tag?: React.ReactNode; place: number; by: string; at: string; note: string | null }) => rows.length === 0 ? null : (
    <section aria-label={title} className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title} <span className="font-normal text-ink-muted">({rows.length})</span></h2>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setPicked((p) => ({ ...p, [kind]: p[kind].length === rows.length ? [] : rows.map((r) => r.id) }))}>{picked[kind].length === rows.length ? 'Clear selection' : 'Select all'}</Button>
          <Button size="sm" disabled={picked[kind].length === 0} onClick={() => setDeciding({ kind, ids: picked[kind], initial: 'approved' })}>Approve or reject selected ({picked[kind].length})</Button>
        </div>
      </div>
      <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
        {rows.map((r) => {
          const l = line(r)
          return (
            <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <input type="checkbox" aria-label={`Select ${l.name}`} checked={picked[kind].includes(r.id)} onChange={() => toggle(kind, r.id)} />
              <div className="min-w-0 flex-1 basis-64">
                <p className="flex flex-wrap items-center gap-2 font-medium">{l.name}{l.tag}</p>
                <p className="mt-0.5 text-xs text-ink-muted">{l.detail} · {places.get(l.place) ?? ''} · {l.by} · {fmtDateTime(l.at)}</p>
                {l.note && <p className="mt-1 text-sm text-ink-muted">{l.note}</p>}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => setDeciding({ kind, ids: [r.id], initial: 'approved' })}>Approve</Button>
                <Button size="sm" variant="outline" className="text-danger" onClick={() => setDeciding({ kind, ids: [r.id], initial: 'rejected' })}>Reject</Button>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )

  return (
    <div className="space-y-6">
      {section('tasks', 'Checklist tasks', data.tasks, (t) => ({ name: t.description, detail: t.checklist, place: t.location_id, by: t.done_by, at: t.done_at, note: t.comment }))}
      {section('readings', 'Monitoring logs', data.readings, (r) => ({
        name: `${r.equipment} - ${r.stage}: ${r.value}`, detail: 'Monitoring log', place: r.location_id, by: r.done_by, at: r.done_at, note: r.comment,
        tag: <Badge tone={r.passed ? 'ok' : 'critical'}>{r.passed ? 'Pass' : 'Fail'}</Badge>,
      }))}
      <DecisionDialog open={deciding !== null} initial={deciding?.initial} title={`Approve or reject ${deciding?.ids.length ?? 0} ${deciding?.kind === 'tasks' ? 'task' : 'log'}${deciding?.ids.length === 1 ? '' : 's'}`}
        onClose={() => setDeciding(null)} onDecide={decide} />
    </div>
  )
}
