import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Person { id: number; name: string; job_title: string }

interface Props {
  name: string
  kind: 'checklists' | 'monitoring'
  approvers: number[] | null
  names?: string[]
  /** Where the choice is saved. */
  path: string
  onClose: () => void
  onSaved: () => void
}

/** Chooses, by name, who approves a checklist or reviews a monitoring log. Any one of them can decide. Nobody ticked means everyone who may, as before. Managers can always step in. */
export function ApproversModal({ name, kind, approvers, names = [], path, onClose, onSaved }: Props) {
  const run = useRun()
  const { data } = useApi<Person[]>(`/approvals/approvers?kind=${kind}`)
  const [chosen, setChosen] = useState<number[]>(approvers ?? [])
  const people = data ?? []
  // people chosen earlier who can no longer approve (a changed role, or left) stay in the list so they can be unticked
  const gone = chosen.map((id, i) => ({ id, label: names[(approvers ?? []).indexOf(id)] ?? `Person ${i + 1}` })).filter((p) => !people.some((x) => x.id === p.id))
  const toggle = (id: number) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))
  const word = kind === 'checklists' ? 'approve it' : 'review its readings'

  async function save() {
    if (await run(() => api(path, { method: 'PUT', body: { approvers: chosen } }), 'Saved')) onSaved()
  }

  return (
    <Modal open title={`Who ${kind === 'checklists' ? 'approves' : 'reviews'} ${name}`} onClose={onClose} size="sm"
      description={`Tick the people who ${word}. Any one of them can decide, and only they see it waiting for approval. Leave everyone unticked and everyone with the permission can, as before. Managers can always step in.`}
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save}>Save</Button></>}>
      <fieldset className="space-y-2">
        <legend className="sr-only">People</legend>
        {people.map((p) => (
          <label key={p.id} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={chosen.includes(p.id)} onChange={() => toggle(p.id)} /> {p.name} <span className="text-ink-muted">- {p.job_title}</span>
          </label>
        ))}
        {gone.map((p) => (
          <label key={p.id} className="flex items-center gap-2 text-sm text-ink-muted">
            <input type="checkbox" checked onChange={() => toggle(p.id)} /> {p.label} (can no longer approve)
          </label>
        ))}
        {data && people.length === 0 && <p className="text-sm text-ink-muted">Nobody has a role that allows this yet. Give a role the permission in Settings first.</p>}
      </fieldset>
    </Modal>
  )
}
