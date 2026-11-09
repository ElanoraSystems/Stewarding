import { ChevronDown, Pencil, Plus } from 'lucide-react'
import { useId } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ActionMenu } from '@/components/ui/action-menu'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { cn } from '@/lib/utils'
import type { EquipmentItem, Schedule } from '@/pages/MonitoringRecordForm'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function when(s: Schedule): string {
  if (s.phase === 'finish') return 'When the time in entry is closed'
  const days = s.weekdays.length ? s.weekdays.map((d) => DAYS[d]).join(', ') : 'Every day'
  const month = s.day_of_month ? `day ${s.day_of_month} of the month` : days
  const timing = s.timing === 'interval' ? `every ${s.interval_minutes} min` : s.timing === 'startup' ? 'at startup' : s.timing === 'manual' ? 'when needed' : 'at a set time'
  return `${month}, ${timing}${s.time_of_day ? ` from ${s.time_of_day.slice(0, 5)}` : ''}`
}

function limits(s: Schedule): string {
  if (s.value_type === 'yes_no') return 'Must be Yes'
  if (s.value_type === 'text') return `Written, up to ${s.max_length ?? 200} characters`
  if (s.value_type === 'choice') return `Choose: ${(s.options ?? []).join(', ')}${s.fail_options?.length ? ` (fails: ${s.fail_options.join(', ')})` : ''}`
  const amber = [s.warn_max != null ? `amber from ${s.warn_max}` : '', s.warn_min != null ? `amber down to ${s.warn_min}` : ''].filter(Boolean).join(', ')
  return `${s.min_value ?? '-'} to ${s.max_value ?? '-'} ${s.unit ?? ''}${amber ? ` (${amber})` : ''}`.trim()
}

/** The one line shown while a point is closed: how many checks it has and when they fall. */
function summary(eq: EquipmentItem): string {
  const active = eq.schedules.filter((s) => s.active)
  const times = [...new Set(active.filter((s) => s.time_of_day && s.timing === 'checkpoint').map((s) => s.time_of_day!.slice(0, 5)))].sort()
  const checks = `${active.length} check${active.length === 1 ? '' : 's'}`
  if (times.length) return `${checks} · ${times.join(', ')}`
  const timings = [...new Set(active.map((s) => (s.timing === 'startup' ? 'at startup' : s.timing === 'interval' ? `every ${s.interval_minutes} min` : s.timing === 'manual' ? 'when needed' : 'set time')))]
  return active.length ? `${checks} · ${timings.join(', ')}` : 'No checks yet'
}

interface Props {
  point: EquipmentItem
  open: boolean
  onToggle: () => void
  canManage: boolean
  onStatus: (status: string) => void
  onRename: () => void
  onWho: () => void
  onApprovers: () => void
  onPointActive: () => void
  onDeletePoint: () => void
  onEditCheck: (schedule: Schedule | null) => void
  onCheckActive: (schedule: Schedule) => void
  onDeleteCheck: (schedule: Schedule) => void
}

/** One monitoring point: a single line while closed, its checks and actions when opened. */
export function MonitoringPointRow({ point: eq, open, onToggle, canManage, onStatus, onRename, onWho, onApprovers, onPointActive, onDeletePoint, onEditCheck, onCheckActive, onDeleteCheck }: Props) {
  const body = useId()
  const limited = eq.visible_to && eq.visible_to.length > 0
  return (
    <section aria-label={eq.name} className={cn('overflow-hidden rounded-2xl border bg-surface', eq.needs_attention ? 'border-warn/60' : 'border-border', !eq.active && 'opacity-75')}>
      <button type="button" aria-expanded={open} aria-controls={body} onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-muted/60">
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-base font-semibold">{eq.name}</span>
            <span className="text-xs text-ink-muted">{eq.code}</span>
          </span>
          <span className="mt-0.5 block text-sm text-ink-muted">{summary(eq)}</span>
        </span>
        <span className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          {!eq.active && <StatusBadge status="inactive" />}
          {eq.active && eq.status !== 'operational' && <StatusBadge status={eq.status} />}
          {eq.needs_attention && <Badge tone="warn">{eq.recent_failures} recent failures</Badge>}
          {eq.approver_names && eq.approver_names.length > 0 && <span title={`Reviewed by: ${eq.approver_names.join(', ')}`}><Badge tone="ok">{eq.approver_names.length} reviewer{eq.approver_names.length === 1 ? '' : 's'}</Badge></span>}
          {limited && <span title={`Only: ${eq.visible_to!.join(', ')}`}><Badge>{eq.visible_to!.length} job title{eq.visible_to!.length === 1 ? '' : 's'}</Badge></span>}
        </span>
        <ChevronDown aria-hidden className={cn('ci-chevron h-5 w-5 shrink-0 text-ink-muted', open && 'rotate-180')} />
      </button>
      <div id={body} className="ci-collapse" data-open={open} aria-hidden={!open} {...(open ? {} : { inert: true })}>
        <div className="overflow-hidden">
          <div className="space-y-4 border-t border-border bg-surface-muted/30 p-4">
            {eq.maintenance_notes && <p className="text-sm text-ink-muted">{eq.maintenance_notes}</p>}
            {limited && <p className="text-sm text-ink-muted">Recorded by: {eq.visible_to!.join(', ')}</p>}
            {eq.approver_names && eq.approver_names.length > 0 && <p className="text-sm text-ink-muted">Reviewed by: {eq.approver_names.join(', ')} (any one of them)</p>}
            {canManage && (
              <div className="flex flex-wrap items-center gap-2">
                <Select aria-label={`Status of ${eq.name}`} className="w-auto" value={eq.status} onChange={(e) => onStatus(e.target.value)}>
                  <option value="operational">Operational</option>
                  <option value="attention">Needs attention</option>
                  <option value="out_of_service">Out of service</option>
                </Select>
                <Button size="sm" variant="outline" onClick={onWho}>Who records it</Button>
                <Button size="sm" variant="outline" onClick={onApprovers}>Who reviews it</Button>
                <ActionMenu label={`More for ${eq.name}`} text="More" actions={[
                  { label: 'Rename', onClick: onRename },
                  { label: eq.active ? 'Make inactive' : 'Make active', onClick: onPointActive },
                  { label: 'Delete', onClick: onDeletePoint, tone: 'danger' },
                ]} />
              </div>
            )}
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {eq.schedules.length === 0 && <li className="px-4 py-3 text-sm text-ink-muted">No checks yet.</li>}
              {eq.schedules.map((s) => (
                <li key={s.id} className={cn('flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3', !s.active && 'opacity-60')}>
                  <div className="min-w-0 flex-1 basis-56">
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {s.stage}
                      {!s.active && <Badge>Inactive</Badge>}
                      {s.require_reference && <Badge>{s.reference_label ?? 'Reference'}</Badge>}
                      {s.trace_lots && <Badge>Food lots</Badge>}
                      {s.phase && <Badge>{s.phase === 'start' ? (s.max_open_minutes ? `Time in, out within ${s.max_open_minutes / 60} h` : 'Time in') : 'Time out'}</Badge>}
                    </p>
                    <p className="mt-0.5 text-sm text-ink-muted">{when(s)}</p>
                  </div>
                  <p className="rounded-lg bg-surface-muted px-3 py-1.5 text-sm font-medium tabular-nums">{limits(s)}</p>
                  {canManage && (
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="outline" onClick={() => onEditCheck(s)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                      <ActionMenu label={`More for ${s.stage}`} actions={[
                        { label: s.active ? 'Make inactive' : 'Make active', onClick: () => onCheckActive(s) },
                        { label: 'Delete', onClick: () => onDeleteCheck(s), tone: 'danger' },
                      ]} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {canManage && <Button size="sm" variant="outline" onClick={() => onEditCheck(null)}><Plus className="h-4 w-4" /> Add check</Button>}
          </div>
        </div>
      </div>
    </section>
  )
}
