import { Download, FileText } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { PRESETS, type Range } from '@/lib/dates'
import { downloadFile } from '@/lib/download'
import { FOOD_GROUPS, MOVEMENTS, REPORTS, SECTIONS, type ReportDef } from '@/lib/reportCatalog'
import { useToast } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { useAllItems } from '@/lib/useItems'
import { cn } from '@/lib/utils'
import { OperationsSummary } from '@/pages/OperationsSummary'
import { ReportPreview, type RecordDoc } from '@/pages/ReportPreview'

type Named = { id: number; name?: string; full_name?: string }

export function ReportsPage() {
  const { me } = useAuth()
  const toast = useToast()
  const canExport = me?.permissions.includes('report.export') ?? false
  const [key, setKey] = useState('attendance')
  const [range, setRange] = useState<Range>(() => PRESETS[0].range() as Range)
  const [locationId, setLocationId] = useState<number | null>(null)
  const [extra, setExtra] = useState<Record<string, string>>({})
  const def = REPORTS.find((r) => r.key === key) as ReportDef
  const has = (f: ReportDef['filters'][number]) => def.filters.includes(f)

  const employees = useApi<{ items: Named[] }>(has('employee') ? '/employees?size=200' : null)
  const suppliers = useApi<Named[]>(has('supplier') ? '/suppliers' : null)
  const points = useApi<Named[]>(has('monitoringPoint') && locationId ? `/equipment${qs({ location_id: locationId })}` : null)
  const { items } = useAllItems()

  const params = {
    date_from: range[0], date_to: range[1], location_id: locationId, employee_id: extra.employee, frequency: extra.frequency,
    equipment_id: has('monitoringPoint') && locationId ? extra.monitoringPoint : '', supplier_id: extra.supplier,
    movement: extra.movement, item_id: extra.item, status: extra.status, food_group: extra.foodGroup,
  }
  const preview = useApi<RecordDoc>(def.summary ? null : `/reports/records/${key}${qs(params)}`)
  const setFilter = (name: string, value: string) => setExtra((e) => ({ ...e, [name]: value }))
  const choose = (next: string) => { setKey(next); setExtra({}) }
  const activePreset = PRESETS.find((p) => p.range()[0] === range[0] && p.range()[1] === range[1])?.key

  async function download(fmt: string) {
    const ok = await downloadFile(`/api/reports/records/${key}/export${qs({ ...params, fmt })}`, `${key}.${fmt}`)
    if (!ok) toast('error', 'Could not create the report. Check the dates and filters.')
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Reports</h1>
      </header>

      <div className="grid gap-6 lg:grid-cols-[17rem_1fr]">
        <nav aria-label="Reports" className="space-y-3 lg:space-y-4">
          {SECTIONS.map((section) => (
            <div key={section} className="flex flex-wrap items-center gap-2 lg:block">
              <p className="px-1 text-xs font-semibold uppercase tracking-wide text-ink-muted lg:mb-1 lg:px-2">{section}</p>
              <ul className="flex flex-wrap gap-2 lg:block lg:space-y-1">
                {REPORTS.filter((r) => r.section === section).map((r) => (
                  <li key={r.key}>
                    <button type="button" onClick={() => choose(r.key)} aria-current={r.key === key}
                      className={cn('flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm hover:bg-surface-muted lg:w-full lg:rounded-md lg:border-transparent lg:bg-transparent lg:py-2 lg:text-left',
                        r.key === key && 'border-brand bg-brand-soft font-medium ring-1 ring-brand lg:bg-surface-muted')}>
                      <FileText className="h-4 w-4 shrink-0 text-brand" aria-hidden /> {r.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <section className="min-w-0 space-y-4" aria-label={def.title}>
          <div>
            <h2 className="text-xl font-semibold">{def.title}</h2>
          </div>

          {def.summary ? <OperationsSummary /> : (
            <>
              <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
                <div className="flex flex-wrap gap-2" role="group" aria-label="Quick date ranges">
                  {PRESETS.map((p) => (
                    <Button key={p.key} size="sm" variant={activePreset === p.key ? 'default' : 'outline'} onClick={() => setRange(p.range() as Range)}>{p.label}</Button>
                  ))}
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <Field label="From"><Input type="date" value={range[0]} max={range[1] || undefined} onChange={(e) => setRange([e.target.value, range[1]])} /></Field>
                  <Field label="To"><Input type="date" value={range[1]} min={range[0]} onChange={(e) => setRange([range[0], e.target.value])} /></Field>
                  <Field label="Location"><LocationSelect allowAll value={locationId} onChange={(id) => { setLocationId(id); setFilter('monitoringPoint', '') }} /></Field>
                  {has('employee') && (
                    <Field label="Employee">
                      <Select value={extra.employee ?? ''} onChange={(e) => setFilter('employee', e.target.value)}>
                        <option value="">Everyone</option>
                        {employees.data?.items.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
                      </Select>
                    </Field>
                  )}
                  {has('frequency') && (
                    <Field label="Checklist">
                      <Select value={extra.frequency ?? ''} onChange={(e) => setFilter('frequency', e.target.value)}>
                        <option value="">Daily and weekly</option>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                      </Select>
                    </Field>
                  )}
                  {has('monitoringPoint') && locationId && (
                    <Field label="Monitoring point">
                      <Select value={extra.monitoringPoint ?? ''} onChange={(e) => setFilter('monitoringPoint', e.target.value)}>
                        <option value="">All points</option>
                        {points.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </Select>
                    </Field>
                  )}
                  {has('supplier') && (
                    <Field label="Supplier">
                      <Select value={extra.supplier ?? ''} onChange={(e) => setFilter('supplier', e.target.value)}>
                        <option value="">All suppliers</option>
                        {suppliers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </Select>
                    </Field>
                  )}
                  {has('movement') && (
                    <Field label="Movement">
                      <Select value={extra.movement ?? ''} onChange={(e) => setFilter('movement', e.target.value)}>
                        <option value="">All movements</option>
                        {MOVEMENTS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                      </Select>
                    </Field>
                  )}
                  {has('foodGroup') && (
                    <Field label="Food group">
                      <Select value={extra.foodGroup ?? ''} onChange={(e) => setFilter('foodGroup', e.target.value)}>
                        <option value="">All food groups</option>
                        {FOOD_GROUPS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                      </Select>
                    </Field>
                  )}
                  {has('status') && def.statuses && (
                    <Field label="Status">
                      <Select value={extra.status ?? ''} onChange={(e) => setFilter('status', e.target.value)}>
                        <option value="">All</option>
                        {def.statuses.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                      </Select>
                    </Field>
                  )}
                  {has('item') && (
                    <Field label="Item">
                      <Select value={extra.item ?? ''} onChange={(e) => setFilter('item', e.target.value)}>
                        <option value="">All items</option>
                        {items.map((i) => <option key={i.id} value={i.id}>{i.code} - {i.name}</option>)}
                      </Select>
                    </Field>
                  )}
                </div>
                {canExport && (
                  <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
                    <Button onClick={() => download('pdf')}><Download className="h-4 w-4" /> Download PDF</Button>
                    <Button variant="outline" onClick={() => download('xlsx')}><Download className="h-4 w-4" /> Excel</Button>
                    <Button variant="outline" onClick={() => download('csv')}><Download className="h-4 w-4" /> CSV</Button>
                  </div>
                )}
              </div>

              <div aria-live="polite">
                {preview.error && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{preview.error}</p>}
                {preview.loading && !preview.data ? <Skeleton className="h-48 w-full" /> : preview.data && (
                  <div className="space-y-3">
                    <p className="text-sm text-ink-muted">{preview.data.period.label}{preview.data.locations.length > 0 && ` - ${preview.data.locations.join(', ')}`}</p>
                    <ReportPreview doc={preview.data} />
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
