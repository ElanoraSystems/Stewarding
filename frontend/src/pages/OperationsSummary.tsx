import { Download } from 'lucide-react'
import { useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState, Skeleton, Table, Td, Th } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { downloadFile } from '@/lib/download'
import { fmtDateTime } from '@/lib/format'
import { useToast } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'

interface Section {
  id: string
  title: string
  columns: { key: string; label: string }[]
  rows: Record<string, string | number | null>[]
  totals: { label: string; value: string | number }[]
}

interface Report {
  period: { type: string; label: string; from: string; to: string }
  locations: string[]
  timezones: string[]
  generated_at: string
  sections: Section[]
}

const FORMATS = [['xlsx', 'Excel'], ['csv', 'CSV'], ['pdf', 'PDF']] as const

export function OperationsSummary() {
  const { me } = useAuth()
  const toast = useToast()
  const canExport = me?.permissions.includes('report.export') ?? false
  const [period, setPeriod] = useState('daily')
  const [anchor, setAnchor] = useState('')
  const [locationId, setLocationId] = useState<number | null>(null)
  const params = { anchor, location_id: locationId }
  const { data, loading, error } = useApi<Report>(`/reports/${period}${qs(params)}`)

  async function download(fmt: string) {
    if (!(await downloadFile(`/api/reports/${period}/export${qs({ ...params, fmt })}`, `report.${fmt}`))) toast('error', 'Export failed')
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Operations summary</h2>
        {canExport && (
          <div className="flex flex-wrap gap-2">
            {FORMATS.map(([fmt, text]) => (
              <Button key={fmt} variant="outline" size="sm" onClick={() => download(fmt)}><Download className="h-4 w-4" /> {text}</Button>
            ))}
          </div>
        )}
      </div>

      <div className="filter-bar">
        <Select aria-label="Report period" className="w-auto" value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </Select>
        <Input aria-label="Report date" type="date" className="w-auto" value={anchor} onChange={(e) => setAnchor(e.target.value)} />
        <LocationSelect allowAll value={locationId} onChange={setLocationId} />
      </div>

      {error && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
      {loading && !data ? <Skeleton className="h-48 w-full" /> : data && (
        <>
          <div className="rounded-md border border-border bg-surface p-3 text-sm">
            <p><strong>{data.period.label}</strong> ({data.period.from} to {data.period.to})</p>
            <p className="text-ink-muted">Locations: {data.locations.join(', ')} - Time zones: {data.timezones.join(', ')}</p>
            <p className="text-ink-muted">Generated {fmtDateTime(data.generated_at)}</p>
          </div>
          {data.sections.map((s) => (
            <Card key={s.id}>
              <CardHeader><CardTitle>{s.title}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {s.totals.length > 0 && (
                  <div className="flex flex-wrap gap-2">{s.totals.map((t) => <Badge key={t.label}>{t.label}: {String(t.value)}</Badge>)}</div>
                )}
                {s.rows.length === 0 ? <EmptyState title="No records for this period" /> : (
                  <Table>
                    <thead><tr>{s.columns.map((c) => <Th key={c.key}>{c.label}</Th>)}</tr></thead>
                    <tbody>
                      {s.rows.map((r, i) => <tr key={i}>{s.columns.map((c) => <Td key={c.key}>{r[c.key] ?? '-'}</Td>)}</tr>)}
                    </tbody>
                  </Table>
                )}
              </CardContent>
            </Card>
          ))}
        </>
      )}
    </div>
  )
}
