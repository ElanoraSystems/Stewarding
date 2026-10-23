import { ChevronRight } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { SECTION_GROUPS } from '@/pages/settings/sections'
import { cn } from '@/lib/utils'

/** The settings sections in groups: a side menu on wide screens and a list to drill into on phones. */
export function SettingsNav() {
  return (
    <nav aria-label="Settings sections" className="space-y-4 lg:sticky lg:top-20 lg:rounded-xl lg:border lg:border-border lg:bg-surface lg:p-3">
      {SECTION_GROUPS.map((group) => (
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
      ))}
    </nav>
  )
}
