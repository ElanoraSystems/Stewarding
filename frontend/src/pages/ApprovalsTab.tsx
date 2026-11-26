import { ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { DecisionDialog, type Decision } from '@/components/DecisionDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtDateTime, fmtLate } from '@/lib/format'
import { useToast } from '@/lib/toast'

export interface TaskWaiting { id: number; description: string; checklist: string; location_id: number; local_date: string; done_by: string; done_at: string; comment: string | null; has_photo: boolean; late_minutes?: number | null; late_reason?: string | null }
export interface ReadingWaiting { id: number; equipment: string; stage: string; value: string; passed: boolean; location_id: number; done_by: string; done_at: string; comment: string | null; control?: string }
export interface Waiting { tasks: TaskWaiting[]; readings: ReadingWaiting[]; count: number }

type Kind = 'tasks' | 'readings'

const SAME_VISIT_MS = 5 * 60 * 1000

/** Readings by one person on one point within five minutes are one visit; visits with a failure come first. */
function visits(rows: ReadingWaiting[]) {
  const out: { equipment: string; by: string; last: number; control: string; readings: ReadingWaiting[] }[] = []
  for (const r of [...rows].sort((a, b) => a.done_at.localeCompare(b.done_at))) {
    const at = Date.parse(r.done_at)
    const v = out.find((x) => x.equipment === r.equipment && x.by === r.done_by && x.readings[0].location_id === r.location_id && at - x.last <= SAME_VISIT_MS)
    if (v) { v.readings.push(r); v.last = at } else out.push({ equipment: r.equipment, by: r.done_by, last: at, control: r.control ?? 'prp', readings: [r] })
  }
  const level = { ccp: 2, oprp: 1, prp: 0 } as Record<string, number>
  const urgency = (v: (typeof out)[number]) => Number(v.readings.some((r) => !r.passed)) * 3 + (level[v.control] ?? 0)  // a failure first, then a CCP, then an OPRP
  return out.sort((a, b) => urgency(b) - urgency(a))
}

/** A group that folds away: one tick, one title and one pair of buttons for everything inside. */
function Fold({ title, label, meta, checked, onCheck, actions, initiallyOpen, children }: { title: string; label: string; meta: string; checked: boolean; onCheck: () => void; actions: ReactNode; initiallyOpen: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(initiallyOpen)
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        <input type="checkbox" aria-label={`Select all of ${label}`} checked={checked} onChange={onCheck} />
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 basis-56 items-center gap-2 text-left">
          <ChevronRight className={`size-4 shrink-0 text-ink-muted transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden />
          <span className="min-w-0"><span className="block font-medium">{title}</span><span className="block text-xs text-ink-muted">{meta}</span></span>
        </button>
        {actions}
      </div>
      {open && children}
    </div>
  )
}

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

  const ask = (kind: Kind, ids: number[], initial: Decision) => setDeciding({ kind, ids, initial })
  const allPicked = (kind: Kind, ids: number[]) => ids.every((id) => picked[kind].includes(id))
  const toggleMany = (kind: Kind, ids: number[]) => setPicked((p) => ({ ...p, [kind]: allPicked(kind, ids) ? p[kind].filter((x) => !ids.includes(x)) : [...new Set([...p[kind], ...ids])] }))
  const decideButtons = (kind: Kind, ids: number[], all = false) => (
    <div className="flex gap-2">
      <Button size="sm" onClick={() => ask(kind, ids, 'approved')}>{all ? 'Approve all' : 'Approve'}</Button>
      <Button size="sm" variant="outline" className="text-danger" onClick={() => ask(kind, ids, 'rejected')}>{all ? 'Reject all' : 'Reject'}</Button>
    </div>
  )
  const header = (kind: Kind, title: string, count: number, ids: number[], extra?: React.ReactNode) => (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-sm font-semibold">{title} <span className="font-normal text-ink-muted">({count})</span></h2>
      <div className="flex flex-wrap gap-2">
        {extra}
        <Button size="sm" variant="ghost" onClick={() => setPicked((p) => ({ ...p, [kind]: p[kind].length === ids.length ? [] : ids }))}>{picked[kind].length === ids.length ? 'Clear selection' : 'Select all'}</Button>
        <Button size="sm" disabled={picked[kind].length === 0} onClick={() => ask(kind, picked[kind], 'approved')}>Approve or reject selected ({picked[kind].length})</Button>
      </div>
    </div>
  )

  const taskGroups = [...data.tasks.reduce((m, t) => m.set(`${t.location_id}|${t.checklist}|${t.local_date}`, [...(m.get(`${t.location_id}|${t.checklist}|${t.local_date}`) ?? []), t]), new Map<string, TaskWaiting[]>()).values()]
  const visitList = visits(data.readings)
  const passedIds = data.readings.filter((r) => r.passed).map((r) => r.id)

  return (
    <div className="space-y-6">
      {data.tasks.length > 0 && (
        <section aria-label="Checklist tasks" className="space-y-2">
          {header('tasks', 'Checklist tasks', data.tasks.length, data.tasks.map((t) => t.id))}
          {taskGroups.map((g) => {
            const ids = g.map((t) => t.id)
            return (
              <Fold key={`${g[0].location_id}${g[0].checklist}${g[0].local_date}`} initiallyOpen={g.length <= 3} checked={allPicked('tasks', ids)} onCheck={() => toggleMany('tasks', ids)}
                label={g[0].checklist} title={g[0].checklist} meta={`${places.get(g[0].location_id) ?? ''} · ${fmtDate(g[0].local_date)} · ${g.length} done`} actions={decideButtons('tasks', ids, true)}>
                <ul className="divide-y divide-border border-t border-border">
                  {g.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-2 pl-11 pr-4">
                      <input type="checkbox" aria-label={`Select ${t.description}`} checked={picked.tasks.includes(t.id)} onChange={() => toggle('tasks', t.id)} />
                      <div className="min-w-0 flex-1 basis-56">
                        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">{t.description}{t.late_minutes ? <Badge tone="warn">Late by {fmtLate(t.late_minutes)}</Badge> : null}</p>
                        <p className="text-xs text-ink-muted">{t.done_by} · {fmtDateTime(t.done_at)}</p>
                        {t.late_minutes ? <p className="mt-0.5 text-sm text-ink-muted">Why it was late: {t.late_reason ?? ''}</p> : null}
                        {t.comment && <p className="mt-0.5 text-sm text-ink-muted">{t.comment}</p>}
                      </div>
                      {decideButtons('tasks', [t.id])}
                    </li>
                  ))}
                </ul>
              </Fold>
            )
          })}
        </section>
      )}
      {data.readings.length > 0 && (
        <section aria-label="Monitoring logs" className="space-y-2">
          {header('readings', 'Monitoring logs', data.readings.length, data.readings.map((r) => r.id),
            passedIds.length < data.readings.length && passedIds.length > 0 && <Button size="sm" variant="outline" onClick={() => setPicked((p) => ({ ...p, readings: passedIds }))}>Select all passed ({passedIds.length})</Button>)}
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {visitList.map((v) => {
              const ids = v.readings.map((r) => r.id)
              const failed = v.readings.filter((r) => !r.passed).length
              return (
                <li key={ids[0]} className={`flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 ${failed ? 'bg-danger/5' : ''}`}>
                  <input type="checkbox" aria-label={`Select ${v.equipment}`} checked={allPicked('readings', ids)} onChange={() => toggleMany('readings', ids)} />
                  <div className="min-w-0 flex-1 basis-64">
                    <p className="flex flex-wrap items-center gap-2 font-medium">{v.equipment}
                      {v.control === 'ccp' && <Badge tone="critical">CCP</Badge>}{v.control === 'oprp' && <Badge tone="warn">OPRP</Badge>}
                      {failed > 0 && <Badge tone="critical">{failed} failed</Badge>}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-muted">{v.by} · {places.get(v.readings[0].location_id) ?? ''} · {fmtDateTime(v.readings[0].done_at)}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {v.readings.map((r) => <Badge key={r.id} tone={r.passed ? 'ok' : 'critical'}>{r.stage}: {r.value}</Badge>)}
                    </div>
                    {v.readings.filter((r) => r.comment).map((r) => <p key={r.id} className="mt-1 text-sm text-ink-muted">{r.stage}: {r.comment}</p>)}
                  </div>
                  {decideButtons('readings', ids, ids.length > 1)}
                </li>
              )
            })}
          </ul>
        </section>
      )}
      <DecisionDialog open={deciding !== null} initial={deciding?.initial} title={`Approve or reject ${deciding?.ids.length ?? 0} ${deciding?.kind === 'tasks' ? 'task' : 'log'}${deciding?.ids.length === 1 ? '' : 's'}`}
        onClose={() => setDeciding(null)} onDecide={decide} />
    </div>
  )
}
