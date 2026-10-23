import { ChevronRight, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Input } from '@/components/ui/input'
import { SECTION_TITLES, SETTINGS } from '@/pages/settings/settingsRegistry'
import { SECTION_GROUPS } from '@/pages/settings/sections'
import { cn } from '@/lib/utils'

/** Section names and the rules on the rules pages that contain the words typed. */
function findSettings(query: string) {
  const needle = query.trim().toLowerCase()
  if (!needle) return null
  const sections = SECTION_GROUPS.flatMap((group) =>
    group.items.filter(([, text]) => text.toLowerCase().includes(needle)).map(([key, text]) => ({ key, title: text, where: group.title })))
  const rules = SETTINGS.filter((s) => s.label.toLowerCase().includes(needle)).map((s) => ({ key: s.section, title: s.label, where: SECTION_TITLES[s.section] }))
  return [...sections, ...rules]
}

/** The settings sections in groups: a side menu on wide screens and a list to drill into on phones. */
export function SettingsNav() {
  const [query, setQuery] = useState('')
  const results = findSettings(query)

  return (
    <nav aria-label="Settings sections" className="space-y-4 lg:sticky lg:top-20 lg:rounded-xl lg:border lg:border-border lg:bg-surface lg:p-3">
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-muted" />
        <Input type="search" aria-label="Search settings" placeholder="Search settings" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      {results ? (
        <ul className="rounded-xl border border-border bg-surface px-3 lg:border-0 lg:bg-transparent lg:px-0">
          {results.length === 0 && <li className="py-3 text-sm text-ink-muted">Nothing matches</li>}
          {results.map((r) => (
            <li key={`${r.where}|${r.title}`} className="border-b border-border last:border-0 lg:border-0">
              <Link to={`/settings/${r.key}`} onClick={() => setQuery('')} className="block min-h-12 py-2 text-[15px] hover:bg-surface-muted lg:min-h-0 lg:rounded-lg lg:px-3 lg:text-sm">
                {r.title}
                <span className="block text-xs text-ink-muted">{r.where}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        SECTION_GROUPS.map((group) => (
          <div key={group.title} role="group" aria-label={group.title}>
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{group.title}</p>
            <ul className="rounded-xl border border-border bg-surface px-3 lg:border-0 lg:bg-transparent lg:px-0">
              {group.items.map(([key, text]) => (
                <li key={key} className="border-b border-border last:border-0 lg:border-0">
                  <NavLink
                    to={`/settings/${key}`}
                    className={({ isActive }) =>
                      cn(
                        'flex min-h-12 items-center justify-between gap-2 text-[15px] lg:min-h-0 lg:rounded-lg lg:px-3 lg:py-2 lg:text-sm',
                        isActive ? 'font-semibold text-brand-deep lg:bg-brand-soft' : 'text-ink lg:hover:bg-surface-muted',
                      )
                    }
                  >
                    {text}
                    <ChevronRight aria-hidden className="h-4 w-4 text-ink-muted lg:hidden" />
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </nav>
  )
}
