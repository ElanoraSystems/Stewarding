import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MonitoringRecordForm, type EquipmentItem } from '@/pages/MonitoringRecordForm'

const mocks = vi.hoisted(() => ({ api: vi.fn(async (_path: string, _options?: unknown) => ({}) as unknown), geofence: false }))

vi.mock('@/lib/api', () => ({ api: mocks.api, uploadFile: vi.fn() }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { geofence: mocks.geofence } }) }))
vi.mock('@/lib/geo', () => ({ currentPosition: async () => ({ latitude: 29.376, longitude: 47.9775, accuracy: 12 }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true } }))
vi.mock('@/lib/useLookups', () => ({ useLookup: () => [] }))

const check = (id: number, stage: string, time: string | null, timing = time ? 'checkpoint' : 'manual') => ({
  id, stage, parameter: 'Temperature', unit: '°C', value_type: 'number', options: null, fail_options: null, max_length: null, require_reference: false, required: true,
  reference_label: null, phase: null, source: 'independent_probe', timing, min_value: 0, max_value: 5, time_of_day: time, interval_minutes: null,
  weekdays: [], day_of_month: null, active: true,
})

const chiller = (checks: ReturnType<typeof check>[]) => ({ id: 1, code: 'CH-1', name: 'Chiller #25', kind: 'Cold storage', location_id: 1, status: 'operational', active: true, supervisor_id: null,
  procedure_reference: null, maintenance_notes: null, visible_to: null, schedules: checks, needs_attention: false, recent_failures: 0 }) as unknown as EquipmentItem

describe('MonitoringRecordForm check choice', () => {
  it('records the check that is due now and gives no drop-down to pick the other time by mistake', async () => {
    render(<MonitoringRecordForm equipment={[chiller([check(1, 'morning_temperature', '08:00:00'), check(2, 'afternoon_temperature', '16:00:00')])]} prefill={null} onSaved={() => {}} onClearRetest={() => {}} />)
    await userEvent.setup().selectOptions(screen.getByLabelText('Monitoring point'), '1')
    expect(screen.queryByRole('combobox', { name: 'Check' })).toBeNull()
    expect(screen.getByText('Afternoon temperature at 16:00')).toBeTruthy()
    expect(screen.getByText(/Also waiting: Morning temperature at 08:00/)).toBeTruthy()
  })

  it('keeps the drop-down for checks that have no time of day, which the clock cannot tell apart', async () => {
    render(<MonitoringRecordForm equipment={[chiller([check(1, 'probe_check', null, 'manual'), check(2, 'door_check', null, 'startup')])]} prefill={null} onSaved={() => {}} onClearRetest={() => {}} />)
    await userEvent.setup().selectOptions(screen.getByLabelText('Monitoring point'), '1')
    expect(screen.getByRole('combobox', { name: 'Check' })).toBeTruthy()
  })

  it('sends where the check was recorded when the organization has a work area, and not when it has none', async () => {
    const user = userEvent.setup()
    for (const geofence of [true, false]) {
      mocks.api.mockClear()
      mocks.geofence = geofence
      const { unmount } = render(<MonitoringRecordForm equipment={[chiller([check(1, 'morning_temperature', '08:00:00')])]} prefill={null} onSaved={() => {}} onClearRetest={() => {}} />)
      await user.selectOptions(screen.getByLabelText('Monitoring point'), '1')
      await user.type(screen.getByLabelText('Temperature'), '3')
      await user.click(screen.getByRole('button', { name: 'Record check' }))
      const body = (mocks.api.mock.calls[0] as unknown as [string, { body: Record<string, unknown> }])[1].body
      expect(body.latitude).toBe(geofence ? 29.376 : undefined)
      unmount()
    }
  })

  it('lets each item of a time in choose how long it takes before its time out is due', async () => {
    const user = userEvent.setup()
    mocks.geofence = false
    mocks.api.mockClear()
    const timeIn = { ...check(1, 'time_in', null, 'manual'), phase: 'start', max_open_minutes: 1440, min_value: -40, max_value: -18 }
    render(<MonitoringRecordForm equipment={[chiller([timeIn as unknown as ReturnType<typeof check>])]} prefill={null} onSaved={() => {}} onClearRetest={() => {}} />)
    await user.selectOptions(screen.getByLabelText('Monitoring point'), '1')
    await user.type(screen.getByLabelText('Temperature'), '20')
    expect(screen.getByRole('option', { name: 'Standard: 24 hours' })).toBeTruthy()
    await user.selectOptions(screen.getByLabelText(/Ready after/), '48')
    await user.click(screen.getByRole('button', { name: 'Record check' }))
    const call = mocks.api.mock.calls.find((c) => String(c[0]).includes('/readings/batch')) as unknown as [string, { body: { readings: { ready_after_minutes: number }[] } }]
    expect(call[1].body.readings[0].ready_after_minutes).toBe(48 * 60)
  })
})

