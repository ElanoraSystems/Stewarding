import { Check, Pencil, X } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface ManagedEntry {
  id: number
  name: string
  active: boolean
}

interface ManagedListProps {
  entries: ManagedEntry[]
  placeholder: string
  onAdd: (name: string) => Promise<boolean>
  onRename: (id: number, name: string) => Promise<boolean>
  onToggle: (id: number, active: boolean) => Promise<boolean>
}

/** Add, rename and retire values of a dropdown list. Values are retired, never deleted, so history keeps its meaning. */
export function ManagedList({ entries, placeholder, onAdd, onRename, onToggle }: ManagedListProps) {
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [text, setText] = useState('')

  async function add() {
    if (draft.trim().length >= 2 && (await onAdd(draft))) setDraft('')
  }

  async function save(id: number) {
    if (await onRename(id, text)) setEditing(null)
  }

  return (
    <div className="space-y-3">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add() }}>
        <Input aria-label={placeholder} placeholder={placeholder} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <Button type="submit" disabled={draft.trim().length < 2}>Add</Button>
      </form>
      {entries.length === 0 ? <p className="py-3 text-sm text-ink-muted">Nothing here yet.</p> : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {entries.map((e) => (
            <li key={e.id} className={cn('flex items-center justify-between gap-2 px-3 py-2 text-sm', !e.active && 'bg-surface-muted text-ink-muted')}>
              {editing === e.id ? (
                <Input aria-label={`Rename ${e.name}`} autoFocus value={text} onChange={(ev) => setText(ev.target.value)}
                  onKeyDown={(ev) => { if (ev.key === 'Enter') save(e.id); if (ev.key === 'Escape') setEditing(null) }} />
              ) : (
                <span className="flex items-center gap-2">{e.name}{!e.active && <Badge>Inactive</Badge>}</span>
              )}
              <span className="flex shrink-0 gap-1">
                {editing === e.id ? (
                  <>
                    <Button size="sm" variant="outline" aria-label="Save name" onClick={() => save(e.id)}><Check className="h-4 w-4" /></Button>
                    <Button size="sm" variant="ghost" aria-label="Cancel rename" onClick={() => setEditing(null)}><X className="h-4 w-4" /></Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" variant="ghost" aria-label={`Rename ${e.name}`} onClick={() => { setEditing(e.id); setText(e.name) }}><Pencil className="h-4 w-4" /></Button>
                    <Button size="sm" variant="outline" onClick={() => onToggle(e.id, !e.active)}>{e.active ? 'Retire' : 'Restore'}</Button>
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
