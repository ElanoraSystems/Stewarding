import { Download } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PRESETS, type Range } from '@/lib/dates'
import { downloadFile } from '@/lib/download'
import { useToast } from '@/lib/toast'
import { qs } from '@/lib/useApi'

const CONTAINS = [
  'A summary: readings, failures, corrective actions, calibrations and late or missed checks',
  'Monitoring records, critical and operational control points first',
  'Corrective actions taken, open and closed',
  'Probe calibration record',
  'Checklist record (with late tasks and why) and the approvals trail',
  'Staff training completed, and the lot register, when there is anything to show',
]

export function InspectorPack({ canExport }: { canExport: boolean }) {
  const toast = useToast()
  const [range, setRange] = useState<Range>(() => PRESETS[0].range() as Range)
  const [locationId, setLocationId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const activePreset = PRESETS.find((p) => p.range()[0] === range[0] && p.range()[1] === range[1])?.key

  async function download() {
    setBusy(true)
    const ok = await downloadFile(`/api/reports/inspector-pack${qs({ date_from: range[0], date_to: range[1], location_id: locationId })}`, 'inspector-pack.pdf')
    setBusy(false)
    if (!ok) toast('error', 'Could not create the inspector pack. Check the dates (at most about three months) and try again.')
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
      <p className="text-sm text-ink-muted">One print-ready PDF with the records a food-safety inspector asks for, for the dates and place you choose:</p>
      <ul className="list-disc space-y-0.5 pl-5 text-sm">{CONTAINS.map((line) => <li key={line}>{line}</li>)}</ul>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Quick date ranges">
        {PRESETS.map((p) => (
          <Button key={p.key} size="sm" variant={activePreset === p.key ? 'default' : 'outline'} onClick={() => setRange(p.range() as Range)}>{p.label}</Button>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="From"><Input type="date" value={range[0]} max={range[1] || undefined} onChange={(e) => setRange([e.target.value, range[1]])} /></Field>
        <Field label="To"><Input type="date" value={range[1]} min={range[0]} onChange={(e) => setRange([range[0], e.target.value])} /></Field>
        <Field label="Location"><LocationSelect allowAll value={locationId} onChange={setLocationId} /></Field>
      </div>
      {canExport ? (
        <div className="border-t border-border pt-3">
          <Button onClick={download} disabled={busy || !range[0] || !range[1]}><Download className="h-4 w-4" /> {busy ? 'Preparing...' : 'Download PDF'}</Button>
        </div>
      ) : <p className="text-sm text-ink-muted">You need permission to export reports to download the inspector pack.</p>}
    </div>
  )
}
