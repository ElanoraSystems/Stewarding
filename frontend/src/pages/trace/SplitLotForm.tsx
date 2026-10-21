import { Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { LotPicker, type LotChoice } from '@/components/LotPicker'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { fmtDate, fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'
import { LabelActions } from '@/pages/trace/LabelActions'
import { RECEIVED_CONDITIONS, type Lot, type Trace } from '@/pages/trace/types'

const blank = () => ({ description: '', count: '1', condition: 'vacuum_chilled', qty: '', unit: '' })

export function SplitLotForm({ onSaved }: { onSaved: () => void }) {
  const run = useRun()
  const [chosen, setChosen] = useState<LotChoice[]>([])
  const [parts, setParts] = useState([blank()])
  const [finish, setFinish] = useState(false)
  const [made, setMade] = useState<Lot[] | null>(null)
  const parent = useApi<Trace>(chosen[0] ? `/lots/${chosen[0].id}` : null).data?.lot
  const thawed = parent?.condition === 'thawed'
  const patch = (index: number, change: Partial<ReturnType<typeof blank>>) => setParts((all) => all.map((p, n) => (n === index ? { ...p, ...change } : p)))

  async function save(event: FormEvent) {
    event.preventDefault()
    let lots: Lot[] = []
    const ok = await run(async () => {
      const result = await api<{ lots: Lot[] }>(`/lots/${chosen[0].id}/split`, { body: {
        finish_parent: finish,
        parts: parts.map((p) => ({ description: p.description, count: Number(p.count), condition: thawed ? 'thawed' : p.condition, qty: p.qty !== '' ? Number(p.qty) : null, unit: p.unit || null })),
      } })
      lots = result.lots
    }, 'Portion lots created')
    if (ok) {
      setMade(lots)
      onSaved()
    }
  }

  if (made) {
    return (
      <div className="space-y-4 rounded-xl border border-border bg-surface p-5">
        <p className="text-sm text-ink-muted">Portion lots created. Print one label per tray or batch and stick it on.</p>
        <ul className="divide-y divide-border rounded-lg border border-border text-sm">
          {made.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <span><span className="font-semibold">{l.code}</span> <span className="text-ink-muted">{l.pack_count} x {l.pack_description} ({l.condition_label})</span></span>
              <span>Use by <span className="font-semibold">{l.use_by ? fmtDateTime(l.use_by) : '-'}</span></span>
            </li>
          ))}
        </ul>
        <LabelActions ids={made.map((l) => l.id)} />
        <Button type="button" variant="outline" onClick={() => { setMade(null); setChosen([]); setParts([blank()]); setFinish(false) }}>Split another lot</Button>
      </div>
    )
  }

  return (
    <form onSubmit={save} className="max-w-3xl space-y-4 rounded-xl border border-border bg-surface p-5">
      <Field label="Lot being opened" hint="Scan the label on the case or main pack, or type its code.">
        <LotPicker max={1} value={chosen} onChange={setChosen} />
      </Field>
      {parent && (
        <p className="rounded-lg bg-surface-muted p-3 text-sm">
          <span className="font-semibold">{parent.item}</span> from {parent.supplier ?? 'unknown supplier'}, supplier lot {parent.supplier_lot ?? '-'}. Produced {parent.produced_on ? fmtDate(parent.produced_on) : '-'},
          expiry {parent.expiry_on ? fmtDate(parent.expiry_on) : '-'}, use by {parent.use_by ? fmtDateTime(parent.use_by) : '-'}. The portions keep these details.
          {thawed && ' This lot is thawed, so its portions stay thawed and cannot be frozen again.'}
        </p>
      )}
      <div className="space-y-3">
        {parts.map((p, i) => (
          <div key={i} className="grid items-end gap-2 sm:grid-cols-[minmax(0,2fr)_5rem_minmax(0,1.4fr)_4.5rem_4.5rem_2.5rem]">
            <Field label={i === 0 ? 'Cut and pack' : ''}><Input required maxLength={120} placeholder="200 g breast portions, vacuum" value={p.description} onChange={(e) => patch(i, { description: e.target.value })} /></Field>
            <Field label={i === 0 ? 'How many' : ''}><Input required type="number" min={1} value={p.count} onChange={(e) => patch(i, { count: e.target.value })} /></Field>
            <Field label={i === 0 ? 'Stored as' : ''}>
              <Select value={thawed ? 'thawed' : p.condition} disabled={thawed} onChange={(e) => patch(i, { condition: e.target.value })}>
                {thawed ? <option value="thawed">Thawed</option> : RECEIVED_CONDITIONS.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
              </Select>
            </Field>
            <Field label={i === 0 ? 'Qty' : ''}><Input type="number" min={0} step="any" value={p.qty} onChange={(e) => patch(i, { qty: e.target.value })} /></Field>
            <Field label={i === 0 ? 'Unit' : ''}><Input maxLength={20} value={p.unit} onChange={(e) => patch(i, { unit: e.target.value })} /></Field>
            {parts.length > 1 ? <Button type="button" variant="ghost" size="icon" aria-label="Remove this cut" onClick={() => setParts((all) => all.filter((_, n) => n !== i))}><Trash2 className="h-4 w-4" /></Button> : <span />}
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={() => setParts((all) => [...all, blank()])}><Plus className="h-4 w-4" /> Add another cut</Button>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={finish} onChange={(e) => setFinish(e.target.checked)} /> Nothing is left of the original pack (mark it used up)</label>
      <Button type="submit" disabled={chosen.length === 0}>Create portion lots and labels</Button>
    </form>
  )
}
