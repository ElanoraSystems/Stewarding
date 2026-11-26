import { Plus } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

type Status = 'never' | 'failed' | 'overdue' | 'due_soon' | 'ok'
interface Check { id: number; calibrated_at: string; by: string; method: string; reference_c: number; reading_c: number; passed: boolean; comment: string | null; deviation?: number }
interface Probe { id: number; code: string; name: string; kind: string; serial_number: string | null; active: boolean; status: Status; due_at: string | null; days_left: number | null; last: Check | null }

const METHODS = [['ice_point', 'Ice water (0 °C)'], ['boiling_point', 'Boiling water (100 °C)'], ['reference', 'Another reference thermometer']] as const
const KINDS = [['probe', 'Probe thermometer'], ['infrared', 'Infrared thermometer'], ['data_logger', 'Data logger']] as const
const STATUS: Record<Status, { text: string; tone: 'ok' | 'warn' | 'critical' }> = {
  ok: { text: 'In date', tone: 'ok' }, due_soon: { text: 'Due soon', tone: 'warn' }, overdue: { text: 'Overdue', tone: 'critical' },
  never: { text: 'Never checked', tone: 'warn' }, failed: { text: 'Failed: do not use', tone: 'critical' },
}
const methodName = (key: string) => METHODS.find((m) => m[0] === key)?.[1] ?? key

/** Thermometers and probes with where their calibration check stands, and the form to record one. */
export function CalibrationPage() {
  const { me } = useAuth()
  const [locationId, setLocationId] = useState<number | null>(null)
  const { data, loading, reload } = useApi<Probe[]>(locationId ? `/calibration/probes${qs({ location_id: locationId })}` : null)
  const [adding, setAdding] = useState(false)
  const [checking, setChecking] = useState<Probe | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const canManage = me?.permissions.includes('equipment.manage') ?? false
  const canRecord = me?.permissions.includes('temp.record') ?? false
  const probes = data ?? []
  const count = (...s: Status[]) => probes.filter((p) => s.includes(p.status)).length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Probe calibration</h1>
        <div className="flex flex-wrap items-center gap-2">
          <LocationSelect value={locationId} onChange={setLocationId} />
          {canManage && <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add probe</Button>}
        </div>
      </div>
      <p className="text-sm text-ink-muted">Check each thermometer against ice water or boiling water. A probe more than 1 °C out must not be used for readings until it passes.</p>

      {probes.length > 0 && (
        <p className="flex flex-wrap gap-2 text-sm" aria-label="Summary">
          <Badge tone={count('failed', 'overdue', 'never') ? 'critical' : 'ok'}>{count('failed', 'overdue', 'never')} need a check</Badge>
          <Badge tone="warn">{count('due_soon')} due soon</Badge>
          <Badge tone="ok">{count('ok')} in date</Badge>
        </p>
      )}

      {loading && !data ? <Skeleton className="h-32 w-full" /> : probes.length === 0 ? (
        <EmptyState title={canManage ? 'No probes here yet. Add each thermometer so its checks are tracked.' : 'No probes here yet. A manager adds the probes used here.'} />
      ) : (
        <ul className="space-y-3">
          {probes.map((p) => (
            <li key={p.id} className="rounded-xl border border-border bg-surface p-4 text-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 text-base font-semibold">{p.name} <span className="text-xs font-normal text-ink-muted">{p.code}</span>
                    <Badge tone={STATUS[p.status].tone}>{STATUS[p.status].text}</Badge></p>
                  <p className="mt-1 text-ink-muted">
                    {p.last ? `Last checked ${fmtDateTime(p.last.calibrated_at)} by ${p.last.by}: read ${p.last.reading_c} °C against ${p.last.reference_c} °C (${methodName(p.last.method)}).` : 'No check on record.'}
                  </p>
                  {p.due_at && p.status !== 'failed' && <p className="text-ink-muted">{p.status === 'overdue' ? `Was due ${fmtDate(p.due_at.slice(0, 10))}` : `Next check due ${fmtDate(p.due_at.slice(0, 10))}`}</p>}
                  {p.last && !p.last.passed && p.last.comment && <p className="mt-1 text-danger">Action taken: {p.last.comment}</p>}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" aria-expanded={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>History</Button>
                  {canRecord && <Button size="sm" onClick={() => setChecking(p)}>Record a check</Button>}
                </div>
              </div>
              {open === p.id && <History probe={p} />}
            </li>
          ))}
        </ul>
      )}
      {adding && locationId && <AddProbe locationId={locationId} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload() }} />}
      {checking && <CheckProbe probe={checking} onClose={() => setChecking(null)} onSaved={() => { setChecking(null); reload() }} />}
    </div>
  )
}

function History({ probe }: { probe: Probe }) {
  const { data } = useApi<Check[]>(`/calibration/probes/${probe.id}/calibrations`)
  if (!data) return <Skeleton className="mt-3 h-16 w-full" />
  if (data.length === 0) return <p className="mt-3 text-ink-muted">Nothing recorded yet.</p>
  return (
    <ul className="mt-3 divide-y divide-border border-t border-border">
      {data.map((c) => (
        <li key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
          <span className="w-40 text-ink-muted">{fmtDateTime(c.calibrated_at)}</span>
          <span>{methodName(c.method)}: read {c.reading_c} °C, reference {c.reference_c} °C ({(c.deviation ?? 0) > 0 ? '+' : ''}{c.deviation} °C)</span>
          <Badge tone={c.passed ? 'ok' : 'critical'}>{c.passed ? 'Passed' : 'Failed'}</Badge>
          <span className="text-ink-muted">{c.by}</span>
          {c.comment && <span className="basis-full text-ink-muted">{c.comment}</span>}
        </li>
      ))}
    </ul>
  )
}

function AddProbe({ locationId, onClose, onSaved }: { locationId: number; onClose: () => void; onSaved: () => void }) {
  const run = useRun()
  const [form, setForm] = useState({ code: '', name: '', kind: 'probe', serial_number: '' })
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const ready = form.code.trim().length >= 2 && form.name.trim().length >= 2
  const save = async () => { if (await run(() => api('/calibration/probes', { body: { ...form, location_id: locationId, serial_number: form.serial_number || null } }), 'Probe added')) onSaved() }
  return (
    <Modal open title="Add a probe" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!ready} onClick={save}>Add probe</Button></>}>
      <div className="space-y-4">
        <Field label="Name"><Input value={form.name} onChange={set('name')} placeholder="Kitchen probe 1" /></Field>
        <Field label="Code (on its label)"><Input value={form.code} onChange={set('code')} placeholder="TH-BH-1" /></Field>
        <Field label="Type"><Select value={form.kind} onChange={set('kind')}>{KINDS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Select></Field>
        <Field label="Serial number (optional)"><Input value={form.serial_number} onChange={set('serial_number')} /></Field>
      </div>
    </Modal>
  )
}

function CheckProbe({ probe, onClose, onSaved }: { probe: Probe; onClose: () => void; onSaved: () => void }) {
  const run = useRun()
  const [method, setMethod] = useState('ice_point')
  const [reading, setReading] = useState('')
  const [reference, setReference] = useState('')
  const [comment, setComment] = useState('')
  const expected = method === 'ice_point' ? 0 : method === 'boiling_point' ? 100 : Number(reference)
  const out = reading !== '' && (method !== 'reference' || reference !== '') && Math.abs(Number(reading) - expected) > 1
  const ready = reading !== '' && (method !== 'reference' || reference !== '') && (!out || comment.trim().length >= 5)
  const save = async () => {
    const body = { method, reading_c: Number(reading), reference_c: method === 'reference' ? Number(reference) : null, comment: comment.trim() || null }
    if (await run(() => api(`/calibration/probes/${probe.id}/calibrations`, { body }), out ? 'Recorded as failed' : 'Calibration recorded')) onSaved()
  }
  return (
    <Modal open title={`Check ${probe.name}`} onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!ready} onClick={save}>Save check</Button></>}>
      <div className="space-y-4">
        <Field label="How was it checked?"><Select value={method} onChange={(e) => setMethod(e.target.value)}>{METHODS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Select></Field>
        {method === 'reference' && <Field label="Reference temperature (°C)"><Input type="number" step="0.1" value={reference} onChange={(e) => setReference(e.target.value)} /></Field>}
        <Field label="What did the probe read? (°C)"><Input type="number" step="0.1" value={reading} onChange={(e) => setReading(e.target.value)} /></Field>
        {out && (
          <div role="alert" className="space-y-2 rounded-lg border border-danger/50 bg-danger-soft p-3 text-sm">
            <p className="font-medium text-danger">More than 1 °C out: this probe fails and must not be used.</p>
            <Field label="What was done about it? (required)"><Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Taken out of use, new probe ordered" /></Field>
          </div>
        )}
      </div>
    </Modal>
  )
}
