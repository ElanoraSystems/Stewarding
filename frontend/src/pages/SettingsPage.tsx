import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { SettingsGeneral } from '@/pages/settings/SettingsGeneral'
import { SettingsInventoryLists } from '@/pages/settings/SettingsInventoryLists'
import { SettingsItems } from '@/pages/settings/SettingsItems'
import { SettingsOrganization } from '@/pages/settings/SettingsOrganization'
import { SettingsRoles } from '@/pages/settings/SettingsRoles'
import { SettingsLocations } from '@/pages/settings/SettingsLocations'
import { SettingsLookups } from '@/pages/settings/SettingsLookups'
import { SettingsMonitoring } from '@/pages/settings/SettingsMonitoring'
import { SettingsShifts } from '@/pages/settings/SettingsShifts'
import { SettingsSuppliers } from '@/pages/settings/SettingsSuppliers'

const TABS = [
  ['organization', 'Organization'],
  ['general', 'Rules & alerts'],
  ['locations', 'Locations'],
  ['shifts', 'Shifts'],
  ['monitoring', 'Monitoring setup'],
  ['items', 'Item master'],
  ['inventory', 'Categories & units'],
  ['suppliers', 'Suppliers'],
  ['lists', 'Dropdown lists'],
  ['roles', 'Roles'],
] as const

type Tab = (typeof TABS)[number][0]

export function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const tab: Tab = TABS.some(([key]) => key === requested) ? (requested as Tab) : 'general'

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <div role="tablist" aria-label="Settings sections" className="flex gap-2 overflow-x-auto pb-1">
        {TABS.map(([key, text]) => (
          <Button key={key} role="tab" aria-selected={tab === key} size="sm" variant={tab === key ? 'default' : 'outline'}
            className="shrink-0" onClick={() => setParams({ tab: key })}>
            {text}
          </Button>
        ))}
      </div>
      {tab === 'organization' && <SettingsOrganization />}
      {tab === 'general' && <SettingsGeneral />}
      {tab === 'locations' && <SettingsLocations />}
      {tab === 'shifts' && <SettingsShifts />}
      {tab === 'monitoring' && <SettingsMonitoring />}
      {tab === 'items' && <SettingsItems />}
      {tab === 'inventory' && <SettingsInventoryLists />}
      {tab === 'suppliers' && <SettingsSuppliers />}
      {tab === 'lists' && <SettingsLookups />}
      {tab === 'roles' && <SettingsRoles />}
    </div>
  )
}
