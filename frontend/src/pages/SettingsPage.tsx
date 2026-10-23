import { ChevronLeft } from 'lucide-react'
import type { ComponentType } from 'react'
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { SettingsGeneral } from '@/pages/settings/SettingsGeneral'
import { SettingsInventoryLists } from '@/pages/settings/SettingsInventoryLists'
import { SettingsItems } from '@/pages/settings/SettingsItems'
import { SettingsLocations } from '@/pages/settings/SettingsLocations'
import { SettingsLookups } from '@/pages/settings/SettingsLookups'
import { SettingsMonitoring } from '@/pages/settings/SettingsMonitoring'
import { SettingsNav } from '@/pages/settings/SettingsNav'
import { SettingsOrganization } from '@/pages/settings/SettingsOrganization'
import { SettingsRoles } from '@/pages/settings/SettingsRoles'
import { SettingsShifts } from '@/pages/settings/SettingsShifts'
import { SettingsSuppliers } from '@/pages/settings/SettingsSuppliers'
import { FIRST_SECTION, isSection, type SectionKey } from '@/pages/settings/sections'

const PAGES: Record<SectionKey, ComponentType> = {
  organization: SettingsOrganization,
  general: SettingsGeneral,
  locations: SettingsLocations,
  shifts: SettingsShifts,
  monitoring: SettingsMonitoring,
  items: SettingsItems,
  inventory: SettingsInventoryLists,
  suppliers: SettingsSuppliers,
  lists: SettingsLookups,
  roles: SettingsRoles,
}

export function SettingsPage() {
  const { section } = useParams()
  const [params] = useSearchParams()
  const desktop = useMediaQuery('(min-width: 1024px)')
  const legacy = params.get('tab')

  if (legacy) return <Navigate to={isSection(legacy) ? `/settings/${legacy}` : '/settings'} replace />
  if (section && !isSection(section)) return <Navigate to="/settings" replace />
  if (!section && desktop) return <Navigate to={`/settings/${FIRST_SECTION}`} replace />

  const Active = isSection(section) ? PAGES[section] : null
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <div className="lg:grid lg:grid-cols-[14rem_minmax(0,1fr)] lg:items-start lg:gap-6">
        <div className={Active ? 'hidden lg:block' : undefined}><SettingsNav /></div>
        {Active && (
          <div className="min-w-0 space-y-4">
            <Link to="/settings" className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-brand-deep lg:hidden">
              <ChevronLeft aria-hidden className="h-4 w-4" /> All settings
            </Link>
            <Active />
          </div>
        )}
      </div>
    </div>
  )
}
