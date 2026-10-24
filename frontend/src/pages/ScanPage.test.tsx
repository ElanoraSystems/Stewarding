import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ScanPage } from '@/pages/ScanPage'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: mocks.api }))

function Landed() {
  const { pathname, state } = useLocation()
  return <p data-testid="landed">{pathname} {JSON.stringify(state)}</p>
}

function visit() {
  render(
    <MemoryRouter initialEntries={['/scan/e7.sig']}>
      <Routes>
        <Route path="scan/:token" element={<ScanPage />} />
        <Route path="*" element={<Landed />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ScanPage', () => {
  it('confirms a monitoring point and opens its form at the right place', async () => {
    mocks.api.mockResolvedValueOnce({ kind: 'equipment', id: 7, name: 'Walk-in fridge', location_id: 2, location_name: 'Main kitchen' })
    visit()
    expect(await screen.findByText('Walk-in fridge')).toBeTruthy()
    expect(mocks.api).toHaveBeenCalledWith('/scan', { body: { token: 'e7.sig' } })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Record a check' }))
    expect(screen.getByTestId('landed').textContent).toBe('/monitoring {"locationId":2,"equipmentId":7}')
  })

  it('opens the checklists for a scanned location', async () => {
    mocks.api.mockResolvedValueOnce({ kind: 'location', id: 2, name: 'Main kitchen', location_id: 2, location_name: 'Main kitchen' })
    visit()
    await userEvent.setup().click(await screen.findByRole('button', { name: "Open today's checklists" }))
    expect(screen.getByTestId('landed').textContent).toContain('/checklists')
  })

  it('says why a code was refused', async () => {
    mocks.api.mockRejectedValueOnce(new Error('This is not a QR code from this system'))
    visit()
    expect((await screen.findByRole('alert')).textContent).toBe('This is not a QR code from this system')
  })
})
