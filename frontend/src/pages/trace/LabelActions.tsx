import { Download, Printer } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { downloadFile, openPdf } from '@/lib/download'
import { useToast } from '@/lib/toast'

/** Prints the 75 x 50 mm labels for some lots, or saves them as ZPL for a Zebra printer. */
export function LabelActions({ ids, copies: start = 1 }: { ids: number[]; copies?: number }) {
  const toast = useToast()
  const [copies, setCopies] = useState(String(start))
  const [dpi, setDpi] = useState('203')
  const count = Math.min(50, Math.max(1, Number(copies) || 1))
  const query = `ids=${ids.join(',')}&copies=${count}`

  async function print() {
    if (!(await openPdf(`/api/lots/labels?${query}`))) toast('error', 'Could not make the labels')
  }

  async function zebra() {
    if (!(await downloadFile(`/api/lots/labels?${query}&fmt=zpl&dpi=${dpi}`, 'lot-labels.zpl'))) toast('error', 'Could not make the Zebra file')
  }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-xs text-ink-muted">
        Copies of each
        <Input aria-label="Copies of each label" type="number" min={1} max={50} className="mt-1 h-9 w-20" value={copies} onChange={(e) => setCopies(e.target.value)} />
      </label>
      <Button type="button" onClick={print}><Printer className="h-4 w-4" aria-hidden /> Print labels</Button>
      <Button type="button" variant="outline" onClick={zebra}><Download className="h-4 w-4" aria-hidden /> Zebra file (ZPL)</Button>
      <Select aria-label="Printer resolution" className="h-9 w-auto" value={dpi} onChange={(e) => setDpi(e.target.value)}>
        <option value="203">203 dpi</option>
        <option value="300">300 dpi</option>
      </Select>
    </div>
  )
}
