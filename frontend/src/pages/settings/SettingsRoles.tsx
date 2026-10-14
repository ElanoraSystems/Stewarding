import { useState, type FormEvent } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { Skeleton, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface RoleRow {
  id: number
  name: string
  label: string
  tier: string
  builtin: boolean
  permissions: string[]
  users: number
}

interface Catalog {
  tiers: string[]
  groups: { group: string; permissions: { key: string; label: string }[] }[]
}

interface Draft {
  id: number | null
  label: string
  tier: string
  permissions: string[]
}

const TIER_HINT: Record<string, string> = {
  supervisor: 'Gets supervisor alerts for their locations and sees the manager-style dashboard.',
  steward: 'Gets steward tasks and the personal dashboard.',
}

export function SettingsRoles() {
  const run = useRun()
  const roles = useApi<RoleRow[]>('/roles')
  const catalog = useApi<Catalog>('/roles/catalog')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [removing, setRemoving] = useState<RoleRow | null>(null)

  const chosen = new Set(draft?.permissions)
  const toggle = (keys: string[], on: boolean) =>
    setDraft((d) => d && { ...d, permissions: [...new Set(on ? [...d.permissions, ...keys] : d.permissions.filter((p) => !keys.includes(p)))] })

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!draft) return
    const body = { label: draft.label, tier: draft.tier, permissions: draft.permissions }
    const ok = await run(() => api(draft.id ? `/roles/${draft.id}` : '/roles', { method: draft.id ? 'PUT' : 'POST', body }), 'Role saved')
    if (ok) {
      setDraft(null)
      roles.reload()
    }
  }

  async function remove() {
    if (removing && await run(() => api(`/roles/${removing.id}`, { method: 'DELETE' }), 'Role deleted')) {
      setRemoving(null)
      roles.reload()
    }
  }

  if (!roles.data || !catalog.data) return <Skeleton className="h-48 w-full" />
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-muted">
          Make a role for any position, choose exactly what it may do, then give it to people from the Employees page. The three built-in roles are fixed; start a new role from one of them to adjust it.
        </p>
        <Button onClick={() => setDraft({ id: null, label: '', tier: 'supervisor', permissions: ['dashboard.view', 'notification.view'] })}>New role</Button>
      </div>
      <Table>
        <thead><tr><Th>Role</Th><Th>Behaves like</Th><Th className="text-right">People</Th><Th className="text-right">Permissions</Th><Th /></tr></thead>
        <tbody>
          {roles.data.map((r) => (
            <tr key={r.id}>
              <Td className="font-medium">{r.label}{r.builtin && <Badge className="ml-2">Built in</Badge>}</Td>
              <Td className="capitalize">{r.tier}</Td>
              <Td className="text-right tabular-nums">{r.users}</Td>
              <Td className="text-right tabular-nums">{r.permissions.length}</Td>
              <Td className="space-x-2 text-right">
                <Button size="sm" variant="outline" onClick={() => setDraft({ id: r.builtin ? null : r.id, label: r.builtin ? '' : r.label, tier: r.tier === 'manager' ? 'supervisor' : r.tier, permissions: r.permissions })}>
                  {r.builtin ? 'Copy' : 'Edit'}
                </Button>
                {!r.builtin && <Button size="sm" variant="outline" disabled={r.users > 0} title={r.users > 0 ? 'Move its people to another role first' : undefined} onClick={() => setRemoving(r)}>Delete</Button>}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>

      <Modal wide open={draft !== null} title={draft?.id ? 'Edit role' : 'New role'} onClose={() => setDraft(null)}>
        {draft && (
          <form onSubmit={save} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Role name"><Input required minLength={2} maxLength={80} placeholder="Head chef" value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} /></Field>
              <Field label="Behaves like" hint={TIER_HINT[draft.tier]}>
                <Select value={draft.tier} onChange={(e) => setDraft({ ...draft, tier: e.target.value })}>
                  {catalog.data.tiers.map((t) => <option key={t} value={t}>{t === 'supervisor' ? 'Supervisor' : 'Steward'}</option>)}
                </Select>
              </Field>
            </div>
            <div className="space-y-3">
              {catalog.data.groups.map((g) => {
                const keys = g.permissions.map((p) => p.key)
                const all = keys.every((k) => chosen.has(k))
                return (
                  <fieldset key={g.group} className="rounded-md border border-border p-3">
                    <legend className="px-1 text-sm font-medium">{g.group}</legend>
                    <label className="mb-2 flex items-center gap-2 text-xs text-ink-muted">
                      <input type="checkbox" checked={all} onChange={(e) => toggle(keys, e.target.checked)} /> Select all
                    </label>
                    <div className="grid gap-1 sm:grid-cols-2">
                      {g.permissions.map((p) => (
                        <label key={p.key} className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={chosen.has(p.key)} onChange={(e) => toggle([p.key], e.target.checked)} /> {p.label}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                )
              })}
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setDraft(null)}>Cancel</Button>
              <Button type="submit" disabled={draft.permissions.length === 0}>Save role</Button>
            </div>
          </form>
        )}
      </Modal>

      <ConfirmDialog open={removing !== null} title="Delete role" message={`"${removing?.label}" will be removed. Nobody has it now.`}
        confirmLabel="Delete" onConfirm={remove} onCancel={() => setRemoving(null)} />
    </div>
  )
}
