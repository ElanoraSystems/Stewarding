import { useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { EmptyState, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Supplier {
  id: number
  name: string
  contact: string | null
  phone: string | null
  email: string | null
  active: boolean
}

const BLANK = { id: null as number | null, name: '', contact: '', phone: '', email: '' }

export function SettingsSuppliers() {
  const run = useRun()
  const { data, reload } = useApi<Supplier[]>('/suppliers?include_inactive=true')
  const [form, setForm] = useState<typeof BLANK | null>(null)

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!form) return
    const body = { name: form.name, contact: form.contact || null, phone: form.phone || null, email: form.email || null }
    const ok = await run(() => form.id ? api(`/suppliers/${form.id}`, { method: 'PUT', body }) : api('/suppliers', { body }), 'Supplier saved')
    if (ok) {
      setForm(null)
      reload()
    }
  }

  async function toggle(s: Supplier) {
    if (await run(() => api(`/suppliers/${s.id}`, { method: 'PUT', body: { active: !s.active } }), s.active ? 'Supplier retired' : 'Supplier restored')) reload()
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-ink-muted">Suppliers are linked to items and to every receiving document, so each invoice is tied to one supplier record.</p>
        <Button onClick={() => setForm({ ...BLANK })}>Add supplier</Button>
      </div>
      <Table>
        <thead><tr><Th>Supplier</Th><Th>Contact</Th><Th>Phone</Th><Th>Email</Th><Th /></tr></thead>
        <tbody>
          {data?.map((s) => (
            <tr key={s.id} className={s.active ? undefined : 'opacity-60'}>
              <Td className="font-medium">{s.name}{!s.active && <Badge className="ml-2">Retired</Badge>}</Td>
              <Td>{s.contact ?? '-'}</Td><Td>{s.phone ?? '-'}</Td><Td>{s.email ?? '-'}</Td>
              <Td className="space-x-2 text-right">
                <Button size="sm" variant="outline" onClick={() => setForm({ id: s.id, name: s.name, contact: s.contact ?? '', phone: s.phone ?? '', email: s.email ?? '' })}>Edit</Button>
                <Button size="sm" variant="outline" onClick={() => toggle(s)}>{s.active ? 'Retire' : 'Restore'}</Button>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.length === 0 && <EmptyState title="No suppliers yet" hint="Add the companies you receive stock from." />}

      <Modal open={form !== null} title={form?.id ? 'Edit supplier' : 'Add supplier'} onClose={() => setForm(null)}>
        {form && (
          <form onSubmit={save} className="space-y-3">
            <Field label="Name"><Input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Contact person"><Input value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Phone"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
              <Field label="Email"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setForm(null)}>Cancel</Button>
              <Button type="submit">Save</Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
