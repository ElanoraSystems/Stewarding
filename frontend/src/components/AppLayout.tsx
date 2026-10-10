import {
  ArrowLeftRight, Bell, CalendarDays, ChartColumn, ClipboardCheck, ClipboardList, Clock, CookingPot, LayoutDashboard,
  LogOut, Menu, ScrollText, Settings, Thermometer, TriangleAlert, UtensilsCrossed, Users, Wrench, X,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

const ICONS: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  employees: Users,
  attendance: Clock,
  roster: CalendarDays,
  'daily-checklists': ClipboardCheck,
  'weekly-checklists': ClipboardList,
  temperature: Thermometer,
  equipment: Wrench,
  crockery: UtensilsCrossed,
  smallware: CookingPot,
  'stock-movements': ArrowLeftRight,
  breakage: TriangleAlert,
  tasks: Bell,
  reports: ChartColumn,
  settings: Settings,
  audit: ScrollText,
}

const ROLE_LABEL = { manager: 'Back of House Manager', supervisor: 'Stewarding Supervisor', steward: 'Steward' }

export function AppLayout() {
  const { me, logout } = useAuth()
  const [open, setOpen] = useState(false)
  if (!me) return null

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16rem_1fr]">
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-border bg-surface transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center justify-between px-5 font-semibold">
          Stewarding Ops
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Close menu" onClick={() => setOpen(false)}>
            <X className="h-5 w-5" />
          </Button>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
          {me.modules.map(({ key, label }) => {
            const Icon = ICONS[key] ?? LayoutDashboard
            return (
              <NavLink
                key={key}
                to={key === 'dashboard' ? '/' : `/${key}`}
                end={key === 'dashboard'}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm',
                    isActive ? 'bg-brand text-brand-ink' : 'text-ink-muted hover:bg-surface-muted hover:text-ink',
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {label}
              </NavLink>
            )
          })}
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="flex min-w-0 flex-col">
        <header className="flex h-16 items-center justify-between gap-3 border-b border-border bg-surface px-4 lg:px-8">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu className="h-5 w-5" />
          </Button>
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right text-sm leading-tight">
              <div className="font-medium">{me.employee?.name ?? me.email}</div>
              <Badge>{ROLE_LABEL[me.role]}</Badge>
            </div>
            <Button variant="outline" size="icon" aria-label="Sign out" onClick={logout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
