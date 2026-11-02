import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsOrganization } from '@/pages/settings/SettingsOrganization'

const mocks = vi.hoisted(() => ({ api: vi.fn(async () => ({})), position: vi.fn() }))
const org = { name: 'Club Seven', legal_name: '', address: '', phone: '', email: '', website: '', registration_number: '', report_footer: '', timezone: 'Asia/Kuwait', currency: '', logo: null,
  latitude: 29.3759, longitude: 47.9774, geofence_radius_m: 150 }

vi.mock('@/lib/api', () => ({ api: mocks.api, uploadLogo: vi.fn() }))
vi.mock('@/lib/geo', () => ({ currentPosition: mocks.position }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true }, useToast: () => vi.fn() }))
vi.mock('@/lib/useApi', () => ({ useApi: () => ({ data: org, reload: () => undefined }) }))
vi.mock('@/components/TimezoneInput', () => ({ TimezoneInput: () => null }))

describe('SettingsOrganization check-in area', () => {
  beforeEach(() => {
    mocks.api.mockClear()
  })

  it('shows the organization area, and saves a changed radius with the other details', async () => {
    const user = userEvent.setup()
    render(<SettingsOrganization />)
    expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('29.3759')
    await user.clear(screen.getByLabelText(/Radius/))
    await user.type(screen.getByLabelText(/Radius/), '300')
    await user.click(screen.getByRole('button', { name: 'Save organization' }))
    expect(mocks.api).toHaveBeenCalledWith('/organization', expect.objectContaining({ method: 'PUT', body: expect.objectContaining({ latitude: 29.3759, longitude: 47.9774, geofence_radius_m: 300 }) }))
  })

  it('fills the area from the current position and can remove the restriction', async () => {
    const user = userEvent.setup()
    mocks.position.mockResolvedValue({ latitude: 29.4, longitude: 47.9 })
    render(<SettingsOrganization />)
    await user.click(screen.getByRole('button', { name: 'Use my current position' }))
    expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('29.400000')
    await user.click(screen.getByRole('button', { name: 'Remove restriction' }))
    await user.click(screen.getByRole('button', { name: 'Save organization' }))
    expect(mocks.api).toHaveBeenLastCalledWith('/organization', expect.objectContaining({ body: expect.objectContaining({ latitude: null, longitude: null, geofence_radius_m: null }) }))
  })
})
