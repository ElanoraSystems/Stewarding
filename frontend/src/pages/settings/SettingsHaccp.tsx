import { ArrowDown, ArrowUp, Download, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { downloadFile } from '@/lib/download'
import { fmtDate } from '@/lib/format'
import { useRun, useToast } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

const KINDS = ['Biological', 'Chemical', 'Physical', 'Allergen']
interface Hazard { step: string; hazard: string; kind: string; significant: boolean; control: string; process: string }
interface Step { name: string; control: '' | 'CCP' | 'OPRP' }
interface Process { name: string; steps: Step[] }
interface Plan { owner: string; team: string; scope: string; products: string; review: string; processes: Process[]; hazards: Hazard[]; revisions: { version: number; date: string; by: string; note: string }[]; version: number; saved: boolean }
interface VersionRow { version: number; current: boolean; saved_at: string | null; by: string; note: string }
const BOX = 'w-full rounded-lg border border-border-strong bg-surface p-2 text-sm'

/** The written part of the HACCP plan. The control points, limits and frequencies are not typed here: the PDF reads them from the monitoring points. */
export function SettingsHaccp() {
  const { data, reload } = useApi<Plan>('/haccp/plan')
  const versions = useApi<VersionRow[]>('/haccp/plan/versions')
  if (!data) return <Skeleton className="h-64 w-full" />
  const refresh = () => { reload(); versions.reload() }
  return <PlanForm key={`${data.version}-${data.revisions.length}-${data.saved}`} plan={data} versions={versions.data ?? []} reload={refresh} />  // a new version or a first save starts the form afresh
}

function PlanForm({ plan, versions, reload }: { plan: Plan; versions: VersionRow[]; reload: () => void }) {
  const { me } = useAuth()
  const run = useRun()
  const toast = useToast()
  const [form, setForm] = useState<Plan>(plan)
  const [locationId, setLocationId] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [restoring, setRestoring] = useState<number | null>(null)
  const canEdit = me?.permissions.includes('equipment.manage') ?? false

  const set = <K extends keyof Plan>(key: K, value: Plan[K]) => setForm((f) => ({ ...f, [key]: value }))
  const row = (i: number, change: Partial<Hazard>) => set('hazards', form.hazards.map((h, j) => (j === i ? { ...h, ...change } : h)))
  const proc = (p: number, change: Partial<Process>) => set('processes', form.processes.map((x, j) => (j === p ? { ...x, ...change } : x)))
  const step = (p: number, i: number, change: Partial<Step>) => proc(p, { steps: form.processes[p].steps.map((s, j) => (j === i ? { ...s, ...change } : s)) })
  const move = (p: number, i: number, by: number) => { const next = [...form.processes[p].steps]; [next[i], next[i + by]] = [next[i + by], next[i]]; proc(p, { steps: next }) }
  const names = form.processes.map((p) => p.name.trim()).filter(Boolean)
  const ready = form.processes.every((p) => p.name.trim().length >= 2 && p.steps.every((s) => s.name.trim().length >= 2)) && new Set(names.map((n) => n.toLowerCase())).size === names.length
    && form.hazards.every((h) => h.step.trim().length >= 2 && h.hazard.trim().length >= 2 && h.control.trim().length >= 2)

  async function save(newVersion: boolean) {
    const { owner, team, scope, products, review, hazards, processes } = form
    if (await run(() => api('/haccp/plan', { method: 'PUT', body: { owner, team, scope, products, review, hazards, processes, new_version: newVersion, note } }), newVersion ? 'Saved as a new version' : 'Saved')) {
      setNote('')
      reload()
    }
  }

  async function download(version: number | null) {
    setBusy(true)
    const ok = await downloadFile(`/api/haccp/plan/pdf${qs({ location_id: locationId, version })}`, 'haccp-plan.pdf')
    setBusy(false)
    if (!ok) toast('error', 'Could not create the HACCP plan. Try again.')
  }

  async function restore(version: number) {
    if (await run(() => api(`/haccp/plan/versions/${version}/restore`, { method: 'POST' }), `Version ${version} restored as a new version`)) {
      setRestoring(null)
      reload()
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">HACCP plan <span className="text-sm font-normal text-ink-muted">version {form.version}{form.saved ? '' : ' (not saved yet)'}</span></h2>
          <p className="text-sm text-ink-muted">Write the team, scope, process flows and hazard analysis here. The critical control points, limits, times and who records and reviews each one are read from your monitoring points, so the printed plan always matches what the kitchens do.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LocationSelect allowAll value={locationId} onChange={setLocationId} />
          <Button onClick={() => download(null)} disabled={busy}><Download className="h-4 w-4" /> {busy ? 'Preparing...' : 'Download PDF'}</Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Plan owner"><Input maxLength={120} disabled={!canEdit} value={form.owner} onChange={(e) => set('owner', e.target.value)} placeholder="Head Chef" /></Field>
        <Field label="HACCP team"><textarea aria-label="HACCP team" rows={2} maxLength={1000} disabled={!canEdit} className={BOX} value={form.team} onChange={(e) => set('team', e.target.value)} placeholder="Names and roles" /></Field>
        <Field label="Scope (outlets and processes covered)"><textarea aria-label="Scope" rows={3} maxLength={2000} disabled={!canEdit} className={BOX} value={form.scope} onChange={(e) => set('scope', e.target.value)} /></Field>
        <Field label="Products and intended use"><textarea aria-label="Products and intended use" rows={3} maxLength={2000} disabled={!canEdit} className={BOX} value={form.products} onChange={(e) => set('products', e.target.value)} /></Field>
      </div>
      <Field label="How and when this plan is reviewed"><textarea aria-label="Review" rows={2} maxLength={1000} disabled={!canEdit} className={BOX} value={form.review} onChange={(e) => set('review', e.target.value)} /></Field>

      <section className="space-y-4" aria-label="Process flows">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Process flows, one for each kind of food</h3>
        <p className="text-sm text-ink-muted">Each kind of food has its own flow of steps in order, from the supplier to the guest. Mark the steps that are critical (CCP) or operational (OPRP) control points; they are shaded on the printed chart.</p>
        {form.processes.map((p, pi) => (
          <div key={pi} className="space-y-3 rounded-lg border border-border bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input aria-label={`Process ${pi + 1} name`} className="w-72 font-semibold" maxLength={60} disabled={!canEdit} value={p.name} onChange={(e) => proc(pi, { name: e.target.value })} />
              {canEdit && <Button size="sm" variant="outline" aria-label={`Remove process ${pi + 1}`} onClick={() => set('processes', form.processes.filter((_, j) => j !== pi))}><Trash2 className="h-4 w-4" /> Remove this process</Button>}
            </div>
            <ol className="flex flex-wrap items-center gap-x-1 gap-y-2" aria-label={`Flow preview of ${p.name}`}>
              {p.steps.map((s, i) => (
                <li key={i} className="flex items-center gap-1 text-sm">
                  <span className={`rounded-md border px-2 py-1 ${s.control === 'CCP' ? 'border-danger bg-danger-soft' : s.control === 'OPRP' ? 'border-warn bg-warn-soft' : 'border-brand bg-brand-soft'}`}>{i + 1}. {s.name || '...'}{s.control && <span className="ml-1 text-xs font-semibold">{s.control}</span>}</span>
                  {i < p.steps.length - 1 && <span aria-hidden className="text-ink-muted">&rarr;</span>}
                </li>
              ))}
            </ol>
            {canEdit && p.steps.map((s, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <Input aria-label={`${p.name} step ${i + 1}`} className="w-80" maxLength={80} value={s.name} onChange={(e) => step(pi, i, { name: e.target.value })} />
                <Select aria-label={`Control level of ${p.name} step ${i + 1}`} className="w-40" value={s.control} onChange={(e) => step(pi, i, { control: e.target.value as Step['control'] })}>
                  <option value="">Not a control step</option><option value="CCP">CCP</option><option value="OPRP">OPRP</option>
                </Select>
                <Button size="sm" variant="outline" aria-label={`Move ${p.name} step ${i + 1} up`} disabled={i === 0} onClick={() => move(pi, i, -1)}><ArrowUp className="h-4 w-4" /></Button>
                <Button size="sm" variant="outline" aria-label={`Move ${p.name} step ${i + 1} down`} disabled={i === p.steps.length - 1} onClick={() => move(pi, i, 1)}><ArrowDown className="h-4 w-4" /></Button>
                <Button size="sm" variant="outline" aria-label={`Remove ${p.name} step ${i + 1}`} onClick={() => proc(pi, { steps: p.steps.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            {canEdit && p.steps.length < 40 && <Button variant="outline" size="sm" onClick={() => proc(pi, { steps: [...p.steps, { name: '', control: '' }] })}><Plus className="h-4 w-4" /> Add a step</Button>}
          </div>
        ))}
        {canEdit && form.processes.length < 12 && <Button variant="outline" size="sm" onClick={() => set('processes', [...form.processes, { name: '', steps: [] }])}><Plus className="h-4 w-4" /> Add a kind of food</Button>}
      </section>

      <section className="space-y-3" aria-label="Hazard analysis">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Hazard analysis</h3>
        <p className="text-sm text-ink-muted">A starting list in general terms. Edit it to your own menu and processes before relying on it, and say which kind of food each hazard applies to.</p>
        {form.hazards.map((h, i) => (
          <div key={i} className="space-y-2 rounded-lg border border-border bg-surface p-3">
            <div className="grid gap-2 sm:grid-cols-[1fr_12rem_9rem_auto]">
              <Input aria-label={`Step ${i + 1}`} placeholder="Process step" maxLength={80} disabled={!canEdit} value={h.step} onChange={(e) => row(i, { step: e.target.value })} />
              <Select aria-label={`Applies to ${i + 1}`} disabled={!canEdit} value={h.process} onChange={(e) => row(i, { process: e.target.value })}>
                <option value="">All processes</option>
                {names.map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
              <Select aria-label={`Type ${i + 1}`} disabled={!canEdit} value={h.kind} onChange={(e) => row(i, { kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</Select>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canEdit} checked={h.significant} onChange={(e) => row(i, { significant: e.target.checked })} /> Significant</label>
            </div>
            <textarea aria-label={`Hazard ${i + 1}`} rows={2} maxLength={400} placeholder="Hazard and its cause" disabled={!canEdit} className={BOX} value={h.hazard} onChange={(e) => row(i, { hazard: e.target.value })} />
            <textarea aria-label={`Control measure ${i + 1}`} rows={2} maxLength={600} placeholder="Control measure" disabled={!canEdit} className={BOX} value={h.control} onChange={(e) => row(i, { control: e.target.value })} />
            {canEdit && <Button size="sm" variant="outline" onClick={() => set('hazards', form.hazards.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /> Remove</Button>}
          </div>
        ))}
        {canEdit && form.hazards.length < 60 && (
          <Button variant="outline" size="sm" onClick={() => set('hazards', [...form.hazards, { step: '', hazard: '', kind: 'Biological', significant: false, control: '', process: '' }])}><Plus className="h-4 w-4" /> Add a hazard</Button>
        )}
      </section>

      {canEdit && (
        <div className="space-y-3 border-t border-border pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <Button disabled={!ready} onClick={() => save(false)}>Save changes</Button>
            <Field label="Or what changed, to save as a new version (the current one is kept as it is)"><Input className="w-80" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Added fish and seafood to cooking" /></Field>
            <Button variant="outline" disabled={!ready || note.trim().length < 3} onClick={() => save(true)}>Save as version {form.version + 1}</Button>
          </div>
        </div>
      )}

      <section aria-label="Version history" className="space-y-2 text-sm">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Version history</h3>
        <p className="text-ink-muted">Every earlier version is kept exactly as it was. Open its PDF, or restore it: it becomes the new current version and nothing is erased.</p>
        <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
          {versions.map((v) => (
            <li key={v.version} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
              <span className="font-medium">Version {v.version}{v.current && <span className="ml-2 rounded-full bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand-deep">Current</span>}</span>
              <span className="text-ink-muted">{v.saved_at ? fmtDate(v.saved_at.slice(0, 10)) : ''}{v.by ? `, ${v.by}` : ''}</span>
              <span className="min-w-0 flex-1">{v.note}</span>
              <Button size="sm" variant="outline" aria-label={`Download version ${v.version} as PDF`} disabled={busy} onClick={() => download(v.version)}><Download className="h-4 w-4" /> PDF</Button>
              {canEdit && !v.current && (restoring === v.version ? (
                <span className="flex items-center gap-2"><span>Make it the new current version?</span><Button size="sm" onClick={() => restore(v.version)}>Yes, restore</Button><Button size="sm" variant="outline" onClick={() => setRestoring(null)}>Cancel</Button></span>
              ) : <Button size="sm" variant="outline" aria-label={`Restore version ${v.version}`} onClick={() => setRestoring(v.version)}>Restore</Button>)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
