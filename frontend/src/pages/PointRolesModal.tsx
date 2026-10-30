import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface RoleOption { name: string; label: string; tier: string }

/** Chooses which roles record a monitoring point. Nothing ticked means every role that can record may. Managers always can. */
export function PointRolesModal({ point, onClose, onSaved }: { point: { id: number; name: string; visible_to: string[] | null }; onClose: () => void; onSaved: () => void }) {
  const run = useRun()
  const roles = useApi<RoleOption[]>('/roles/options')
  const [chosen, setChosen] = useState<string[]>(point.visible_to ?? [])
  const options = (roles.data ?? []).filter((r) => r.tier !== 'manager')
  const toggle = (name: string) => setChosen((c) => (c.includes(name) ? c.filter((n) => n !== name) : [...c, name]))

  async function save() {
    if (await run(() => api(`/equipment/${point.id}`, { method: 'PUT', body: { visible_to: chosen } }), 'Saved')) onSaved()
  }

  return (
    <Modal open title={`Who records ${point.name}`} onClose={onClose} size="sm"
      description="Tick the roles that see and record this log. Leave all unticked and everyone who can record monitoring sees it. Managers always see it."
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save}>Save</Button></>}>
      <fieldset className="space-y-2">
        <legend className="sr-only">Roles</legend>
        {options.map((r) => (
          <label key={r.name} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={chosen.includes(r.name)} onChange={() => toggle(r.name)} /> {r.label}
          </label>
        ))}
        {roles.data && options.length === 0 && <p className="text-sm text-ink-muted">There are no other roles to choose from.</p>}
      </fieldset>
    </Modal>
  )
}
