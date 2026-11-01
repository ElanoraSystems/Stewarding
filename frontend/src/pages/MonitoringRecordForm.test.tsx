import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MonitoringRecordForm, type EquipmentItem } from '@/pages/MonitoringRecordForm'

vi.mock('@/lib/api', () => ({ api: vi.fn(), uploadFile: vi.fn() }))
vi.mock('@/lib/toast', () => ({ useRun: () => async () => true }))
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
})
