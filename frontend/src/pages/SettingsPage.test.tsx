import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsPage } from '@/pages/SettingsPage'

const screenSize = vi.hoisted(() => ({ desktop: true }))
vi.mock('@/lib/useMediaQuery', () => ({ useMediaQuery: () => screenSize.desktop }))

vi.mock('@/pages/settings/SettingsRules', () => ({ SettingsRules: ({ section }: { section: string }) => <p>Rules {section} page</p> }))
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

  it('opens a rules topic as its own section', () => {
    visit('/settings/monitoring-rules')
    expect(screen.getByText('Rules monitoring-rules page')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Monitoring rules' }).getAttribute('aria-current')).toBe('page')
  })

  it('sends the old Rules & alerts address, as a path or a ?tab=, to Attendance rules', () => {
    visit('/settings/general')
    expect(where()).toBe('/settings/attendance')
    expect(screen.getByText('Rules attendance page')).toBeTruthy()
  })

  it('sends the old ?tab=general link to Attendance rules', () => {
    visit('/settings?tab=general')
    expect(where()).toBe('/settings/attendance')
  })

  it('finds a rule by its words and opens the page it lives on', async () => {
    screenSize.desktop = false
    const user = userEvent.setup()
    visit('/settings')
    await user.type(screen.getByRole('searchbox', { name: 'Search settings' }), 'grace')
    expect(screen.queryByRole('group', { name: 'Company' })).toBeNull()
    const hit = screen.getByRole('link', { name: /Grace period for a due check/ })
    expect(hit.textContent).toContain('Monitoring rules')
    await user.click(hit)
    expect(where()).toBe('/settings/monitoring-rules')
    expect((screen.getByRole('searchbox', { name: 'Search settings' }) as HTMLInputElement).value).toBe('')
  })

  it('finds a section by its name and says so when nothing matches', async () => {
    screenSize.desktop = false
    const user = userEvent.setup()
    visit('/settings')
    const box = screen.getByRole('searchbox', { name: 'Search settings' })
    await user.type(box, 'suppl')
    expect(screen.getByRole('link', { name: /Suppliers/ }).getAttribute('href')).toBe('/settings/suppliers')
    await user.clear(box)
    await user.type(box, 'zzzz')
    expect(screen.getByText('Nothing matches')).toBeTruthy()
  })

  it('does not mistake an object property name for a section', () => {
    screenSize.desktop = false
    visit('/settings/constructor')
    expect(where()).toBe('/settings')
  })

  it('treats an unknown ?tab= as no section at all', () => {
    screenSize.desktop = false
    visit('/settings?tab=nope')
    expect(where()).toBe('/settings')
  })
})
