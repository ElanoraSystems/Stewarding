import { Download } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/table'
import { downloadFile } from '@/lib/download'
import { useToast } from '@/lib/toast'
import { useApi } from '@/lib/useApi'
import { ReportPreview, type RecordDoc } from '@/pages/ReportPreview'

/** Pick a lot by its code and see where it came from and everywhere it went, with the same report to download. */
export function RecallTab({ initialCode = '' }: { initialCode?: string }) {
  const toast = useToast()
  const [typed, setTyped] = useState(initialCode)
  const [code, setCode] = useState(initialCode)
  const lot = useApi<{ id: number; code: string }>(code ? `/lots/by-code/${encodeURIComponent(code)}` : null)
  const trace = useApi<RecordDoc>(lot.data ? `/lots/${lot.data.id}/recall` : null)

  async function download(fmt: 'pdf' | 'xlsx') {
    if (!lot.data || !(await downloadFile(`/api/lots/${lot.data.id}/recall/export?fmt=${fmt}`, `recall-${lot.data.code}.${fmt}`))) toast('error', 'Could not create the report')
  }

  return (
    <section className="space-y-4" aria-label="Recall trace">
      <p className="text-sm text-ink-muted">
        Type the lot code (it is on the label) to see where the food came from, everywhere it went and every check that named it.
        To trace all of one supplier&apos;s deliveries in a period, use Reports, Lot recall trace.
      </p>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setCode(typed.trim()) }}>
        <Field label="Lot code"><Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="For example B2610-884" /></Field>
        <Button type="submit" disabled={!typed.trim()}>Show trace</Button>
        {trace.data && (
          <>
            <Button type="button" variant="outline" onClick={() => download('pdf')}><Download className="h-4 w-4" aria-hidden /> PDF</Button>
            <Button type="button" variant="outline" onClick={() => download('xlsx')}><Download className="h-4 w-4" aria-hidden /> Excel</Button>
          </>
        )}
      </form>
      {lot.error && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{lot.error}</p>}
      {(lot.loading || trace.loading) && !trace.data ? <Skeleton className="h-40 w-full" /> : trace.data && <ReportPreview doc={trace.data} />}
    </section>
  )
}
