import { Plus, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { EmptyState } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { label } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { CheckFormModal } from '@/pages/CheckFormModal'
import { JobTitlesModal } from '@/pages/JobTitlesModal'
import { MonitoringPointRow } from '@/pages/MonitoringPointRow'
import { FormBuilderModal } from '@/pages/FormBuilderModal'
import { TimesEditor } from '@/pages/TimesEditor'
import type { EquipmentItem, Schedule } from '@/pages/MonitoringRecordForm'

interface Template {
  key: string
  name: string
  type: string
  times: string[] | null
  checks: { stage: string; parameter: string; unit: string | null; value_type: string; min_value: number | null; max_value: number | null; timing: string; phase: string | null }[]
}

export function EquipmentPage({ embedded = false }: { embedded?: boolean }) {
  const { me } = useAuth()
  const run = useRun()
  const canManage = me?.permissions.includes('equipment.manage') ?? false
  const canDeleteReadings = me?.permissions.includes('equipment.delete') ?? false
  const [locationId, setLocationId] = useState<number | null>(null)
  const { data, reload } = useApi<EquipmentItem[]>(locationId ? `/equipment${qs({ location_id: locationId })}` : null)
  const [limiting, setLimiting] = useState<EquipmentItem | null>(null)
  const [editing, setEditing] = useState<{ equipmentId: number; schedule: Schedule | null } | null>(null)
  const [adding, setAdding] = useState(false)
  const [find, setFind] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [openIds, setOpenIds] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState<{ kind: 'point' | 'check'; id: number; name: string } | null>(null)
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null)
  const [presetOpen, setPresetOpen] = useState(false)
  const [preset, setPreset] = useState('')
  const [presetName, setPresetName] = useState('')
  const [presetTimes, setPresetTimes] = useState<string[]>([])
  const [onDemand, setOnDemand] = useState(false)
  const templates = useApi<Template[]>(canManage ? '/equipment/templates' : null)
  const chosen = templates.data?.find((t) => t.key === preset)
  const needle = find.trim().toLowerCase()
  const shown = (data ?? []).filter((e) => (showInactive || e.active) && (!needle || [e.name, e.code, ...e.schedules.map((s) => s.stage)].some((t) => t.toLowerCase().includes(needle))))
  const kinds = new Map<string, EquipmentItem[]>()
  for (const e of shown) kinds.set(e.kind, [...(kinds.get(e.kind) ?? []), e])

  async function setStatus(eq: EquipmentItem, status: string) {
    if (await run(() => api(`/equipment/${eq.id}`, { method: 'PUT', body: { status } }), 'Status updated')) reload()
  }

  async function setPointActive(eq: EquipmentItem) {
    if (await run(() => api(`/equipment/${eq.id}`, { method: 'PUT', body: { active: !eq.active } }), eq.active ? 'Made inactive' : 'Made active')) reload()
  }

  async function setCheckActive(s: Schedule) {
    if (await run(() => api(`/equipment/schedules/${s.id}/active`, { method: 'PUT', body: { active: !s.active } }), s.active ? 'Made inactive' : 'Made active')) reload()
  }

  async function confirmDelete() {
    if (!deleting) return
    const path = deleting.kind === 'point' ? `/equipment/${deleting.id}` : `/equipment/schedules/${deleting.id}`
    if (await run(() => api(`${path}${canDeleteReadings ? '?with_readings=true' : ''}`, { method: 'DELETE' }), 'Deleted')) {
      setDeleting(null)
      reload()
    }
  }

  async function rename(event: FormEvent) {
    event.preventDefault()
    if (renaming && await run(() => api(`/equipment/${renaming.id}`, { method: 'PUT', body: { name: renaming.name.trim() } }), 'Name updated')) {
      setRenaming(null)
      reload()
    }
  }

  async function addFromTemplate(event: FormEvent) {
    event.preventDefault()
    const ok = await run(() => api('/equipment/from-template', { body: { template: preset, location_id: locationId, name: presetName || null, times: chosen?.times && !onDemand ? presetTimes.map((t) => t.slice(0, 5)) : undefined, on_demand: onDemand || undefined } }), 'Monitoring point added')
    if (ok) {
      setPresetOpen(false)
      setPreset('')
      setPresetName('')
      setOnDemand(false)
      reload()
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {embedded ? <h2 className="text-lg font-semibold">Monitoring points and checks</h2> : <h1 className="text-2xl font-semibold">Monitoring Setup</h1>}
        <div className="flex flex-wrap gap-3">
          <LocationSelect value={locationId} onChange={setLocationId} />
          {canManage && <Button onClick={() => setPresetOpen(true)}><Plus className="h-4 w-4" /> From template</Button>}
          {canManage && <Button variant="outline" onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Create form</Button>}
        </div>
      </div>

      {data?.length === 0 && <EmptyState title="No monitoring points at this location" />}
      {data && data.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-52 flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden />
            <Input aria-label="Find a monitoring point" placeholder="Find a point or a check" className="pl-9" value={find} onChange={(e) => setFind(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Show inactive ({data.filter((e) => !e.active).length})</label>
          <span className="text-sm text-ink-muted">{data.filter((e) => e.active).length} active of {data.length}</span>
          <span className="ml-auto flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpenIds(new Set(shown.map((e) => e.id)))}>Open all</Button>
            <Button size="sm" variant="ghost" onClick={() => setOpenIds(new Set())}>Close all</Button>
          </span>
        </div>
      )}
      {data && data.length > 0 && shown.length === 0 && <EmptyState title="No monitoring point matches" />}
      {[...kinds].map(([kind, points]) => (
        <section key={kind} aria-label={label(kind)} className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">{label(kind)} <span className="font-normal">({points.length})</span></h3>
          {points.map((eq) => (
            <MonitoringPointRow key={eq.id} point={eq} canManage={canManage} open={openIds.has(eq.id) || find.trim() !== ''}
              onToggle={() => setOpenIds((ids) => { const next = new Set(ids); if (!next.delete(eq.id)) next.add(eq.id); return next })}
              onStatus={(status) => setStatus(eq, status)} onRename={() => setRenaming({ id: eq.id, name: eq.name })} onWho={() => setLimiting(eq)}
              onPointActive={() => setPointActive(eq)} onDeletePoint={() => setDeleting({ kind: 'point', id: eq.id, name: eq.name })}
              onEditCheck={(schedule) => setEditing({ equipmentId: eq.id, schedule })} onCheckActive={setCheckActive}
              onDeleteCheck={(s) => setDeleting({ kind: 'check', id: s.id, name: s.stage })} />
          ))}
        </section>
      ))}

      <ConfirmDialog open={deleting !== null} title={deleting?.kind === 'point' ? 'Delete monitoring point' : 'Delete check'}
        message={canDeleteReadings
          ? `Delete ${deleting?.name ?? ''}? If it has recorded readings, they will be deleted as well, together with their corrective actions. This cannot be undone.`
          : `Delete ${deleting?.name ?? ''}? This cannot be undone. Anything with recorded readings cannot be deleted; make it inactive instead.`}
        confirmLabel="Delete" onConfirm={confirmDelete} onCancel={() => setDeleting(null)} />

      {limiting && <JobTitlesModal point={limiting} onClose={() => setLimiting(null)} onSaved={() => { setLimiting(null); reload() }} />}
      {editing && <CheckFormModal equipmentId={editing.equipmentId} schedule={editing.schedule} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}

      <Modal open={presetOpen} title="Add from template" description="A ready-made monitoring point with its checks and limits." onClose={() => setPresetOpen(false)}
        footer={<>
          <Button type="button" variant="outline" onClick={() => setPresetOpen(false)}>Cancel</Button>
          <Button type="submit" form="template-form" disabled={!preset || !locationId || (!!chosen?.times && !onDemand && (presetTimes.some((t) => !t) || new Set(presetTimes).size !== presetTimes.length))}>Add monitoring point</Button>
        </>}>
        <form id="template-form" onSubmit={addFromTemplate} className="space-y-5">
          <Field label="Template">
            <Select required value={preset} onChange={(e) => { setPreset(e.target.value); setOnDemand(false); setPresetTimes(templates.data?.find((t) => t.key === e.target.value)?.times ?? []) }}>
              <option value="">Select</option>
              {templates.data?.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
            </Select>
          </Field>
          {chosen && (
            <ul className="list-inside list-disc text-sm text-ink-muted">
              {chosen.checks.map((c, i) => (
                <li key={i}>{c.stage}: {c.value_type === 'yes_no' ? 'yes or no' : `${c.parameter} ${c.min_value ?? '-'} to ${c.max_value ?? '-'} ${c.unit ?? ''}`}</li>
              ))}
            </ul>
          )}
          {chosen?.times && (
            <div role="radiogroup" aria-label="When it is recorded" className="grid grid-cols-2 gap-2">
              {([[false, 'At set times'], [true, 'When needed']] as const).map(([value, text]) => (
                <button key={text} type="button" role="radio" aria-checked={onDemand === value} onClick={() => setOnDemand(value)}
                  className={`rounded-xl border px-3 py-2.5 text-sm font-semibold ${onDemand === value ? 'border-brand bg-brand/10 text-brand-deep' : 'border-border text-ink-muted hover:bg-surface-muted'}`}>{text}</button>
              ))}
              {onDemand && <p className="col-span-2 text-sm text-ink-muted">No set time: it is recorded whenever the work is done, and is never shown as due or overdue.</p>}
            </div>
          )}
          {chosen?.times && !onDemand && <Field label={chosen.checks.some((c) => c.phase) ? 'Times a day items go in (the time out follows each)' : 'Times a day (one check at each, all in this monitoring point)'}><TimesEditor times={presetTimes} onChange={setPresetTimes} /></Field>}
          <Field label="Name (optional)"><Input value={presetName} maxLength={120} onChange={(e) => setPresetName(e.target.value)} /></Field>
        </form>
      </Modal>

      <Modal open={renaming !== null} size="sm" title="Rename monitoring point" onClose={() => setRenaming(null)}
        footer={<>
          <Button type="button" variant="outline" onClick={() => setRenaming(null)}>Cancel</Button>
          <Button type="submit" form="rename-form" disabled={!renaming || renaming.name.trim().length < 2}>Save name</Button>
        </>}>
        <form id="rename-form" onSubmit={rename} className="space-y-3">
          <Field label="Name"><Input required minLength={2} maxLength={120} value={renaming?.name ?? ''} onChange={(e) => setRenaming((r) => r && { ...r, name: e.target.value })} /></Field>
        </form>
      </Modal>

      {adding && <FormBuilderModal initialLocation={locationId} onClose={() => setAdding(false)} onCreated={() => { setAdding(false); reload() }} />}
    </div>
  )
}
