import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MyShiftCard } from '@/pages/MyShiftCard'

const mocks = vi.hoisted(() => ({ rostered: [] as unknown[] }))
vi.mock('@/lib/auth', () => ({
  useAuth: () => ({ me: { permissions: [], locations: [
    { id: 1, name: 'Main Kitchen', timezone: 'Asia/Kuwait', geofence: false },
    { id: 2, name: 'Banquet Hall', timezone: 'Asia/Kuwait', geofence: false },
  ] } }),
}))
vi.mock('@/lib/toast', () => ({ useRun: () => async () => true, useToast: () => () => undefined }))
vi.mock('@/lib/useApi', () => ({
  useApi: () => ({
    loading: false,
    reload: () => undefined,
    data: { checked_in: false, server_time: '', employee: 'Sam', employee_code: 'E002', record: null, incomplete_task_count: 0, face_required: false, face_enrolled: false, rostered_today: mocks.rostered },
  }),
}))

describe('MyShiftCard', () => {
  it('shows where today is rostered and preselects that location first', () => {
    mocks.rostered = [{ location_id: 2, location_name: 'Banquet Hall', shift: 'Morning', start: '06:00', end: '14:00', week_off: false }]
    render(<MyShiftCard />)
    expect(screen.getByText(/Morning, 06:00 to 14:00, at/)).toBeTruthy()
    const select = screen.getByLabelText('Location') as HTMLSelectElement
    expect(select.value).toBe('2')
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(['Banquet Hall (rostered today)', 'Main Kitchen'])
  })

  it('says so on a week off and when nothing is rostered', () => {
    mocks.rostered = [{ location_id: 1, location_name: 'Main Kitchen', shift: 'Week off', start: '00:00', end: '00:00', week_off: true }]
    const { unmount } = render(<MyShiftCard />)
    expect(screen.getByText('Week off at Main Kitchen')).toBeTruthy()
    unmount()
    mocks.rostered = []
    render(<MyShiftCard />)
    expect(screen.getByText('You are not on the roster today.')).toBeTruthy()
  })
})
