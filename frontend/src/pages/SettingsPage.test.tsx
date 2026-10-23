import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsPage } from '@/pages/SettingsPage'

const screenSize = vi.hoisted(() => ({ desktop: true }))
vi.mock('@/lib/useMediaQuery', () => ({ useMediaQuery: () => screenSize.desktop }))

vi.mock('@/pages/settings/SettingsGeneral', () => ({ SettingsGeneral: () => <p>Rules page</p> }))
vi.mock('@/pages/settings/SettingsInventoryLists', () => ({ SettingsInventoryLists: () => <p>Units page</p> }))
vi.mock('@/pages/settings/SettingsItems', () => ({ SettingsItems: () => <p>Items page</p> }))
vi.mock('@/pages/settings/SettingsLocations', () => ({ SettingsLocations: () => <p>Locations page</p> }))
vi.mock('@/pages/settings/SettingsLookups', () => ({ SettingsLookups: () => <p>Lists page</p> }))
vi.mock('@/pages/settings/SettingsMonitoring', () => ({ SettingsMonitoring: () => <p>Monitoring page</p> }))
vi.mock('@/pages/settings/SettingsOrganization', () => ({ SettingsOrganization: () => <p>Organization page</p> }))
vi.mock('@/pages/settings/SettingsRoles', () => ({ SettingsRoles: () => <p>Roles page</p> }))
vi.mock('@/pages/settings/SettingsShifts', () => ({ SettingsShifts: () => <p>Shifts page</p> }))
vi.mock('@/pages/settings/SettingsSuppliers', () => ({ SettingsSuppliers: () => <p>Suppliers page</p> }))

function Where() {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}

function visit(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/:section" element={<SettingsPage />} />
      </Routes>
      <Where />
    </MemoryRouter>,
  )
}

const where = () => screen.getByTestId('where').textContent

describe('SettingsPage', () => {
  beforeEach(() => {
    screenSize.desktop = true
  })

  it('sends an old ?tab= link to the clean address of that section', () => {
    visit('/settings?tab=monitoring')
    expect(where()).toBe('/settings/monitoring')
    expect(screen.getByText('Monitoring page')).toBeTruthy()
  })

  it('opens the first section on a wide screen and lists the groups beside it', () => {
    visit('/settings')
    expect(where()).toBe('/settings/organization')
    expect(screen.getByText('Organization page')).toBeTruthy()
    for (const group of ['Company', 'People', 'Food safety', 'Stock', 'Lists']) expect(screen.getByRole('group', { name: group })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Monitoring setup' }).getAttribute('aria-current')).toBeNull()
  })

  it('marks the open section in the menu', () => {
    visit('/settings/roles')
    expect(screen.getByRole('link', { name: 'Roles' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByText('Roles page')).toBeTruthy()
  })

  it('shows only the list of sections on a phone, and a way back once one is open', () => {
    screenSize.desktop = false
    visit('/settings')
    expect(where()).toBe('/settings')
    expect(screen.getByRole('link', { name: 'Suppliers' })).toBeTruthy()
    expect(screen.queryByText('Organization page')).toBeNull()
  })

  it('offers All settings on a phone inside a section', () => {
    screenSize.desktop = false
    visit('/settings/suppliers')
    expect(screen.getByText('Suppliers page')).toBeTruthy()
    expect(screen.getByRole('link', { name: /All settings/ }).getAttribute('href')).toBe('/settings')
  })

  it('sends an unknown section or tab back to the settings list', () => {
    screenSize.desktop = false
    visit('/settings/nope')
    expect(where()).toBe('/settings')
  })

  it('treats an unknown ?tab= as no section at all', () => {
    screenSize.desktop = false
    visit('/settings?tab=nope')
    expect(where()).toBe('/settings')
  })
})
