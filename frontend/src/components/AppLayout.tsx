import {
  ArrowLeftRight, Bell, CalendarDays, ChartColumn, ClipboardCheck, Clock, LayoutDashboard, Package,
  LogOut, Menu, ScrollText, Settings, Thermometer, TriangleAlert, Users, Wrench, X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { BrandMark } from '@/components/BrandMark'
import { NotificationBell } from '@/components/NotificationBell'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { APP_NAME } from '@/lib/brand'
import { setDisplayTimeZone } from '@/lib/format'
import { useApi } from '@/lib/useApi'
import { cn } from '@/lib/utils'

const ICONS: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  employees: Users,
  attendance: Clock,
  roster: CalendarDays,
  checklists: ClipboardCheck,
  monitoring: Thermometer,
  equipment: Wrench,
  inventory: Package,
  'stock-movements': ArrowLeftRight,
  breakage: TriangleAlert,
  tasks: Bell,
  reports: ChartColumn,
  settings: Settings,
  audit: ScrollText,
}

const GROUPS: { title: string; keys: string[] }[] = [
  { title: 'Overview', keys: ['dashboard', 'tasks'] },
  { title: 'People', keys: ['employees', 'attendance', 'roster'] },
  { title: 'Daily operations', keys: ['checklists'] },
  { title: 'Food safety', keys: ['monitoring', 'equipment'] },
  { title: 'Stock', keys: ['inventory', 'stock-movements', 'breakage'] },
  { title: 'Insights and admin', keys: ['reports', 'settings', 'audit'] },
]

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('')

export function AppLayout() {
  const { me, logout } = useAuth()
  const { pathname } = useLocation()
  const org = useApi<{ name: string; logo: string | null; timezone: string }>('/organization')
  const reloadOrg = org.reload
  setDisplayTimeZone(org.data?.timezone)
  useEffect(() => {
    window.addEventListener('organization-changed', reloadOrg)
    return () => window.removeEventListener('organization-changed', reloadOrg)
  }, [reloadOrg])
  const [open, setOpen] = useState(false)
  if (!me) return null

  const name = me.employee?.name ?? me.email
  const known = new Set(GROUPS.flatMap((g) => g.keys))
  const groups = [...GROUPS, { title: 'More', keys: me.modules.map((m) => m.key).filter((k) => !known.has(k)) }]
    .map(({ title, keys }) => ({ title, modules: keys.flatMap((k) => me.modules.filter((m) => m.key === k)) }))
    .filter((g) => g.modules.length > 0)
  const current = me.modules.find(({ key }) => (key === 'dashboard' ? pathname === '/' : pathname === `/${key}` || pathname.startsWith(`/${key}/`)))

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[17.5rem_1fr] lg:gap-2 lg:p-3">
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-72 flex-col bg-side text-white transition-transform lg:sticky lg:top-3 lg:h-[calc(100vh-1.5rem)] lg:w-auto lg:translate-x-0 lg:rounded-2xl',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center justify-between px-5">
          <BrandMark organization={org.data?.name ?? ''} hasLogo={!!org.data?.logo} inverse />
          <Button variant="ghost" size="icon" className="text-white hover:bg-white/10 lg:hidden" aria-label="Close menu" onClick={() => setOpen(false)}>
            <X className="h-5 w-5" />
          </Button>
        </div>
        <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 pb-4">
          {groups.map(({ title, modules }) => (
            <div key={title} role="group" aria-label={title} className="space-y-0.5">
              <p className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-white/40">{title}</p>
              {modules.map(({ key, label }) => {
            const Icon = ICONS[key] ?? LayoutDashboard
            return (
              <NavLink
                key={key}
                to={key === 'dashboard' ? '/' : `/${key}`}
                end={key === 'dashboard'}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-xl px-3 py-1.5 text-sm transition-colors',
                    isActive ? 'bg-white/12 font-medium text-white' : 'text-white/65 hover:bg-white/8 hover:text-white',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span className={cn('flex h-7 w-7 items-center justify-center rounded-lg', isActive ? 'bg-brand text-white' : 'bg-white/8')}>
                      <Icon className="h-4 w-4 shrink-0" aria-hidden />
                    </span>
                    {label}
                  </>
                )}
              </NavLink>
            )
              })}
            </div>
          ))}
        </nav>
        <div className="m-3 flex items-center gap-3 rounded-xl bg-white/8 p-3">
          <Link to="/account" title="Change password" className="flex min-w-0 flex-1 items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-white">
            <span aria-hidden className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold">{initials(name)}</span>
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-medium">{name}</span>
              <span className="block truncate text-xs text-white/60">{me.role_label}</span>
            </span>
          </Link>
          <Button variant="ghost" size="icon" className="text-white hover:bg-white/10" aria-label="Sign out" onClick={logout}>
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/40 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="flex min-w-0 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 px-4 lg:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu className="h-5 w-5" />
          </Button>
          <nav aria-label="Breadcrumb" className="hidden text-sm text-ink-muted sm:block">
            {APP_NAME} <span aria-hidden>/</span> <span className="font-medium text-ink">{current?.label ?? 'Home'}</span>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <NotificationBell />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-8 lg:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
