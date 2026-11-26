import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MyShiftCard } from '@/pages/MyShiftCard'

const mocks = vi.hoisted(() => ({ status: {} as Record<string, unknown>, api: vi.fn(), position: vi.fn(), byLocation: true }))
vi.mock('@/lib/auth', () => ({
  useAuth: () => ({ me: { permissions: [], geofence: true, by_location: mocks.byLocation, locations: [{ id: 1, name: 'Main Kitchen', timezone: 'Asia/Kuwait' }, { id: 2, name: 'Back Burner', timezone: 'Asia/Kuwait' }] } }),
}))
vi.mock('@/lib/toast', () => ({ useRun: () => async () => true, useToast: () => () => undefined }))
vi.mock('@/lib/useApi', () => ({ useApi: () => ({ loading: false, reload: () => undefined, data: mocks.status }) }))
vi.mock('@/lib/geo', () => ({ currentPosition: () => mocks.position() }))
vi.mock('@/lib/api', async () => ({ ...(await vi.importActual<object>('@/lib/api')), api: (...a: unknown[]) => mocks.api(...a) }))
vi.mock('@/components/FaceCapture', () => ({ FaceCapture: () => <p>Camera</p> }))

const base = {
  checked_in: false, server_time: '', employee: 'Sam', employee_code: 'E002', record: null, incomplete_task_count: 0, face_required: false, face_enrolled: true,
  rostered_today: [{ location_id: 1, location_name: 'Main Kitchen', shift: 'Morning', start: '06:00', end: '14:00', week_off: false }],
}

describe('check in and out flow', () => {
  beforeEach(() => {
    mocks.status = { ...base }
    mocks.api.mockReset()
    mocks.position.mockReset()
    mocks.byLocation = true
  })

  it('welcomes the person with the time and place once checked in', async () => {
    mocks.position.mockResolvedValue({ latitude: 1, longitude: 1, accuracy: 5 })
    mocks.api.mockResolvedValue({ check_in_at: '2026-10-31T04:58:00Z', late_minutes: 0 })
    render(<MyShiftCard />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByText('You are checked in')).toBeTruthy()
    expect(screen.getByText('On time')).toBeTruthy()
    expect(screen.getByText(/at Main Kitchen/)).toBeTruthy()
  })

  it('asks the person to choose where they are when the server cannot tell, instead of guessing', async () => {
    mocks.byLocation = false
    mocks.status = { ...base, rostered_today: [] }
    mocks.position.mockResolvedValue({ latitude: 1, longitude: 1, accuracy: 5 })
    mocks.api.mockRejectedValueOnce(new Error('Choose a location to check in at'))
    render(<MyShiftCard />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Check in' }))
    const picker = await screen.findByRole('combobox', { name: 'Location' })
    expect((picker as HTMLSelectElement).value).toBe('')  // nothing pre-selected
    expect((screen.getByRole('button', { name: 'Check in' }) as HTMLButtonElement).disabled).toBe(true)
    mocks.api.mockResolvedValue({ check_in_at: '2026-10-31T04:58:00Z', late_minutes: 0 })
    await user.selectOptions(picker, 'Back Burner')
    await user.click(screen.getByRole('button', { name: 'Check in' }))
    expect(mocks.api).toHaveBeenLastCalledWith('/attendance/check-in', expect.objectContaining({ body: expect.objectContaining({ location_id: 2 }) }))
  })

  it('shows the lateness on the welcome screen', async () => {
    mocks.position.mockResolvedValue({ latitude: 1, longitude: 1, accuracy: 5 })
    mocks.api.mockResolvedValue({ check_in_at: '2026-10-31T05:10:00Z', late_minutes: 10 })
    render(<MyShiftCard />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByText('10 min late')).toBeTruthy()
  })

  it('explains a wrong position and offers to check it again', async () => {
    mocks.position.mockResolvedValue({ latitude: 1, longitude: 1, accuracy: 5 })
    mocks.api.mockRejectedValue(new Error('You are about 212 m from Main Kitchen. You can check in only within 100 m'))
    render(<MyShiftCard />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByText('We could not confirm where you are')).toBeTruthy()
    expect(screen.getByText(/about 212 m from Main Kitchen/)).toBeTruthy()
    mocks.api.mockResolvedValue({ check_in_at: '2026-10-31T04:58:00Z', late_minutes: 0 })
    await user.click(screen.getByRole('button', { name: 'Check my location again' }))
    expect(await screen.findByText('You are checked in')).toBeTruthy()
  })

  it('says the face is not enrolled instead of opening the camera, and goes back to the start', async () => {
    mocks.status = { ...base, face_required: true, face_enrolled: false }
    render(<MyShiftCard />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByText('Your face is not enrolled yet')).toBeTruthy()
    expect(screen.queryByText('Camera')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Back to start' }))
    await waitFor(() => expect(screen.queryByText('Your face is not enrolled yet')).toBeNull())
  })

  it('opens the face check full screen when the face check is on and the face is enrolled', async () => {
    mocks.status = { ...base, face_required: true }
    mocks.api.mockResolvedValue({ required: true, token: 't', steps: ['turn_left'] })
    render(<MyShiftCard />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Check in' }))
    expect(await screen.findByText('Camera')).toBeTruthy()
    expect(screen.getByRole('dialog', { name: 'Check in with your face' })).toBeTruthy()
  })

  it('shows the running time while on duty and a summary after checking out', async () => {
    const since = new Date(Date.now() - 3 * 3600 * 1000).toISOString()
    mocks.status = { ...base, checked_in: true, record: { check_in_at: since, late_minutes: 0 }, location: { id: 1, name: 'Main Kitchen', timezone: 'Asia/Kuwait' }, shift: 'Morning', incomplete_task_count: 0 }
    mocks.api.mockResolvedValue({})
    render(<MyShiftCard />)
    expect(screen.getByText('On duty')).toBeTruthy()
    expect(screen.getByText(/^3:00:0\d$/)).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: /Check out/ }))
    expect(await screen.findByText('Shift complete. Thank you.')).toBeTruthy()
    expect(screen.getByText('3h 00m')).toBeTruthy()
  })
})
