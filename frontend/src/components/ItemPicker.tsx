import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { Item } from '@/lib/useItems'
import { cn } from '@/lib/utils'

interface Props {
  items: Item[]
  value: string
  onChange: (id: string) => void
  label?: string
  placeholder?: string
  className?: string
}

const SHOWN = 50

/** Type to find an item by code or name; arrow keys and Enter pick one. Replaces a drop-down that has to be scrolled. */
export function ItemPicker({ items, value, onChange, label = 'Item', placeholder = 'Type a code or name', className }: Props) {
  const chosen = items.find((i) => String(i.id) === value)
  const text = chosen ? `${chosen.code} - ${chosen.name}` : ''
  const [typed, setTyped] = useState<string | null>(null)  // null: showing the chosen item, not a search
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const listId = useId()

  const matches = useMemo(() => {
    const words = (typed ?? '').toLowerCase().split(/\s+/).filter(Boolean)
    const found = words.length ? items.filter((i) => words.every((w) => `${i.code} ${i.name}`.toLowerCase().includes(w))) : items
    return { list: found.slice(0, SHOWN), more: Math.max(0, found.length - SHOWN) }
  }, [items, typed])

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) {
        setOpen(false)
        setTyped(null)
      }
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const pick = (item: Item) => {
    onChange(String(item.id))
    setTyped(null)
    setOpen(false)
  }

  function keys(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setAt((n) => Math.min(n + 1, matches.list.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setAt((n) => Math.max(n - 1, 0))
    } else if (e.key === 'Enter' && open && matches.list[at]) {
      e.preventDefault()
      pick(matches.list[at])
    } else if (e.key === 'Escape') {
      setOpen(false)
      setTyped(null)
    }
  }

  return (
    <div ref={box} className={cn('relative', className)}>
      <input
        role="combobox" aria-label={label} aria-expanded={open} aria-controls={listId} aria-autocomplete="list" autoComplete="off"
        className="h-10 w-full rounded-lg border border-border-strong bg-surface px-3 text-sm pointer-coarse:h-11 focus-visible:outline-2 focus-visible:outline-brand"
        placeholder={placeholder} value={typed ?? text}
        onFocus={(e) => { setOpen(true); e.currentTarget.select() }}
        onChange={(e) => { setTyped(e.target.value); setOpen(true); setAt(0); if (e.target.value === '') onChange('') }}
        onKeyDown={keys}
      />
      {open && (
        <ul id={listId} role="listbox" className="absolute z-30 mt-1 max-h-64 w-full min-w-64 overflow-auto rounded-lg border border-border bg-surface py-1 shadow-lg">
          {matches.list.length === 0 && <li className="px-3 py-2 text-sm text-ink-muted">No item matches</li>}
          {matches.list.map((it, n) => (
            <li key={it.id} role="option" aria-selected={String(it.id) === value}
              className={cn('cursor-pointer px-3 py-2 text-sm', n === at && 'bg-brand-soft', String(it.id) === value && 'font-semibold')}
              onMouseEnter={() => setAt(n)} onMouseDown={(e) => { e.preventDefault(); pick(it) }}>
              <span className="text-ink-muted">{it.code}</span> {it.name}
            </li>
          ))}
          {matches.more > 0 && <li className="px-3 py-2 text-xs text-ink-muted">{matches.more} more. Keep typing to narrow the list.</li>}
        </ul>
      )}
    </div>
  )
}
