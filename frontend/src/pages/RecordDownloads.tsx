import { Download } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { downloadFile } from '@/lib/download'
import { useToast } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function monthRange(offset: number): [string, string] {
  const now = new Date()
  return [iso(new Date(now.getFullYear(), now.getMonth() + offset, 1)), iso(new Date(now.getFullYear(), now.getMonth() + offset + 1, 0))]
}

export function RecordDownloads() {
  const toast = useToast()
  const [kind, setKind] = useState('monitoring')
  const [locationId, setLocationId] = useState<number | null>(null)
  const [equipmentId, setEquipmentId] = useState('')
  const [from, setFrom] = useState(() => iso(new Date()))
  const [to, setTo] = useState(() => iso(new Date()))
  const points = useApi<{ id: number; name: string }[]>(locationId && kind === 'monitoring' ? `/equipment${qs({ location_id: locationId })}` : null)

  async function download(fmt: string) {
    const params = { fmt, date_from: from, date_to: to, location_id: locationId, equipment_id: kind === 'monitoring' ? equipmentId : '' }
    const ok = await downloadFile(`/api/reports/records/${kind}/export${qs(params)}`, `${kind}-record.${fmt}`)
    if (!ok) toast('error', 'Could not create the record. Check the dates and location.')
  }

  const setRange = ([a, b]: [string, string]) => {
    setFrom(a)
    setTo(b)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Records for audit and month end</CardTitle>
        <p className="text-sm text-ink-muted">
          A titled document per location and monitoring point or checklist: who recorded each reading, when, the result,
          who approved it and any corrective action. Choose a day, a month or your own dates.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Record">
            <Select value={kind} onChange={(e) => { setKind(e.target.value); setEquipmentId('') }}>
              <option value="monitoring">Monitoring record</option>
              <option value="checklists">Checklist record</option>
            </Select>
          </Field>
          <Field label="Location"><LocationSelect allowAll value={locationId} onChange={(id) => { setLocationId(id); setEquipmentId('') }} /></Field>
          {kind === 'monitoring' && locationId && (
            <Field label="Monitoring point">
              <Select value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)}>
                <option value="">All points</option>
                {points.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </Field>
          )}
          <Field label="From"><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
          <Field label="To"><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setRange([iso(new Date()), iso(new Date())])}>Today</Button>
          <Button size="sm" variant="outline" onClick={() => setRange(monthRange(0))}>This month</Button>
          <Button size="sm" variant="outline" onClick={() => setRange(monthRange(-1))}>Last month</Button>
          <span className="mx-2 h-5 w-px bg-border" aria-hidden />
          <Button size="sm" onClick={() => download('pdf')}><Download className="h-4 w-4" /> PDF</Button>
          <Button size="sm" variant="outline" onClick={() => download('xlsx')}><Download className="h-4 w-4" /> Excel</Button>
          <Button size="sm" variant="outline" onClick={() => download('csv')}><Download className="h-4 w-4" /> CSV</Button>
        </div>
      </CardContent>
    </Card>
  )
}
