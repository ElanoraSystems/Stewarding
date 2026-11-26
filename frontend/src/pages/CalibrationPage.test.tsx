import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CalibrationPage } from '@/pages/CalibrationPage'

const mocks = vi.hoisted(() => ({ api: vi.fn(async (_path: string, _options?: unknown) => ({}) as unknown), permissions: ['temp.view', 'temp.record'] as string[] }))
const last = { id: 1, calibrated_at: '2026-10-01T08:00:00Z', by: 'Sam', method: 'ice_point', reference_c: 0, reading_c: 0.3, passed: true, comment: null }
const probes = [
  { id: 1, code: 'TH-1', name: 'Kitchen probe', kind: 'probe', serial_number: null, active: true, status: 'overdue', due_at: '2026-10-31T08:00:00Z', days_left: -5, last },
  { id: 2, code: 'TH-2', name: 'Bar probe', kind: 'probe', serial_number: null, active: true, status: 'ok', due_at: '2026-12-20T08:00:00Z', days_left: 20, last },
  { id: 3, code: 'TH-3', name: 'Old probe', kind: 'probe', serial_number: null, active: true, status: 'failed', due_at: null, days_left: null, last: { ...last, passed: false, reading_c: 3, comment: 'Taken out of use' } },
]

vi.mock('@/lib/api', () => ({ api: mocks.api }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { permissions: mocks.permissions, locations: [{ id: 2, name: 'Beach Kitchen' }] } }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => (await action(), true) }))
vi.mock('@/lib/useApi', () => ({ qs: () => '', useApi: (path: string | null) => ({ data: path ? probes : null, loading: false, reload: () => undefined }) }))

describe('CalibrationPage', () => {
  beforeEach(() => mocks.api.mockClear())

  it('shows where each probe stands and counts the ones needing a check', () => {
    render(<CalibrationPage />)
    expect(screen.getByText('Overdue')).toBeTruthy()
    expect(screen.getByText('In date')).toBeTruthy()
    expect(screen.getByText('Failed: do not use')).toBeTruthy()
    expect(screen.getByText('2 need a check')).toBeTruthy()
    expect(screen.getByText(/Action taken: Taken out of use/)).toBeTruthy()
  })

  it('records a good check straight away, but a probe out by more than a degree needs a note', async () => {
    const user = userEvent.setup()
    render(<CalibrationPage />)
    await user.click(screen.getAllByRole('button', { name: 'Record a check' })[0])
    await user.type(screen.getByLabelText(/What did the probe read/), '3')
    expect(screen.getByRole('alert').textContent).toContain('More than 1')
    expect((screen.getByRole('button', { name: 'Save check' }) as HTMLButtonElement).disabled).toBe(true)
    await user.type(screen.getByLabelText(/What was done about it/), 'Replaced the probe')
    await user.click(screen.getByRole('button', { name: 'Save check' }))
    expect(mocks.api).toHaveBeenCalledWith('/calibration/probes/1/calibrations', { body: { method: 'ice_point', reading_c: 3, reference_c: null, comment: 'Replaced the probe' } })
  })

  it('offers adding a probe and recording only to those allowed', () => {
    mocks.permissions = ['temp.view']
    render(<CalibrationPage />)
    expect(screen.queryByRole('button', { name: 'Record a check' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Add probe/ })).toBeNull()
    mocks.permissions = ['temp.view', 'temp.record']
  })
})
