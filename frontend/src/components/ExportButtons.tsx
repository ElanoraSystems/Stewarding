import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { iso } from '@/lib/dates'
import { downloadFile } from '@/lib/download'
import { useToast } from '@/lib/toast'
import { qs } from '@/lib/useApi'

interface Props {
  kind: string  // the record behind the list, for example "receipts" or "movements"
  filters: Record<string, string | number | null>  // the filters on screen, passed as they are
  from: string
  to: string  // with no dates chosen the last 30 days are exported
}

/** Downloads what the list above shows, with the same filters, so the list and its report cannot disagree. */
export function ExportButtons({ kind, filters, from, to }: Props) {
  const toast = useToast()

  async function download(fmt: 'pdf' | 'xlsx' | 'csv') {
    const today = new Date()
    const start = new Date(today.getTime() - 29 * 86_400_000)
    const params = { ...filters, date_from: from || (to ? to : iso(start)), date_to: to || iso(today), fmt }
    if (!(await downloadFile(`/api/reports/records/${kind}/export${qs(params)}`, `${kind}.${fmt}`))) {
      toast('error', 'Could not create the file. Check the dates and filters.')
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-ink-muted">Download this list{from || to ? '' : ' (last 30 days)'}:</span>
      <Button size="sm" variant="outline" onClick={() => download('pdf')}><Download className="h-4 w-4" /> PDF</Button>
      <Button size="sm" variant="outline" onClick={() => download('xlsx')}><Download className="h-4 w-4" /> Excel</Button>
      <Button size="sm" variant="outline" onClick={() => download('csv')}><Download className="h-4 w-4" /> CSV</Button>
    </div>
  )
}
