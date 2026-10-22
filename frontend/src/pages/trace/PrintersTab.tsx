import { useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Printer {
  id: number
  name: string
  host: string
  port: number
  dpi: number
  active: boolean
}

/** Network Zebra printers the server sends labels to; a manager adds each by its address and checks it with a test label. */
export function PrintersTab() {
  const run = useRun()
  const { data, reload } = useApi<Printer[]>('/label-printers')
  const [form, setForm] = useState({ name: '', host: '', port: '9100', dpi: '203' })
  const set = (key: keyof typeof form, value: string) => setForm((f) => ({ ...f, [key]: value }))

  async function add(event: FormEvent) {
    event.preventDefault()
    if (await run(() => api('/label-printers', { body: { name: form.name, host: form.host, port: Number(form.port), dpi: Number(form.dpi) } }), 'Printer added')) {
      setForm({ name: '', host: '', port: '9100', dpi: '203' })
      reload()
    }
  }

  const toggle = async (p: Printer) => {
    if (await run(() => api(`/label-printers/${p.id}`, { method: 'PUT', body: { name: p.name, host: p.host, port: p.port, dpi: p.dpi, active: !p.active } }), p.active ? 'Printer switched off' : 'Printer switched on')) reload()
  }
  const remove = async (p: Printer) => {
    if (await run(() => api(`/label-printers/${p.id}`, { method: 'DELETE' }), 'Printer removed')) reload()
  }
  const test = (p: Printer) => run(() => api(`/label-printers/${p.id}/test`, { method: 'POST', body: {} }), `Test label sent to ${p.name}`)

  if (!data) return <Skeleton className="h-48 w-full" />
  return (
    <div className="space-y-4">
      <form onSubmit={add} className="flex flex-wrap items-end gap-3">
        <Field label="Name"><Input required minLength={2} maxLength={60} className="w-48" placeholder="Butchery Zebra" value={form.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="IP address or network name"><Input required maxLength={120} className="w-52" placeholder="192.168.1.50" value={form.host} onChange={(e) => set('host', e.target.value)} /></Field>
        <Field label="Port"><Input required type="number" min={1} max={65535} className="w-24" value={form.port} onChange={(e) => set('port', e.target.value)} /></Field>
        <Field label="Resolution">
          <Select className="w-32" value={form.dpi} onChange={(e) => set('dpi', e.target.value)}>
            <option value="203">203 dpi</option>
            <option value="300">300 dpi</option>
            <option value="600">600 dpi</option>
          </Select>
        </Field>
        <Button type="submit">Add printer</Button>
      </form>
      <Table>
        <thead><tr><Th>Printer</Th><Th>Address</Th><Th>Resolution</Th><Th>Status</Th><Th /></tr></thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.id}>
              <Td className="font-medium">{p.name}</Td>
              <Td>{p.host}:{p.port}</Td>
              <Td>{p.dpi} dpi</Td>
              <Td><Badge tone={p.active ? 'ok' : 'neutral'}>{p.active ? 'On' : 'Off'}</Badge></Td>
              <Td className="space-x-2 text-right">
                <Button size="sm" variant="outline" onClick={() => test(p)}>Print a test label</Button>
                <Button size="sm" variant="outline" onClick={() => toggle(p)}>{p.active ? 'Switch off' : 'Switch on'}</Button>
                <Button size="sm" variant="outline" onClick={() => remove(p)}>Remove</Button>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data.length === 0 && <p className="text-sm text-ink-muted">No label printers yet.</p>}
    </div>
  )
}
