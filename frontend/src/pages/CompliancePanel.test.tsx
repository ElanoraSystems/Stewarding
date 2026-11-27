import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LimitTrend } from '@/components/LimitTrend'
import { CompliancePanel, MissedByHour } from '@/pages/CompliancePanel'

const mocks = vi.hoisted(() => ({ paths: [] as (string | null)[], data: null as unknown }))
vi.mock('@/lib/useApi', async (original) => ({
  ...(await original<typeof import('@/lib/useApi')>()),
  useApi: (path: string | null) => { mocks.paths.push(path); return { data: mocks.data, loading: false, error: null, reload: vi.fn() } },
}))

const hours = (at: Record<number, number>) => Array.from({ length: 24 }, (_, h) => at[h] ?? 0)
const outlet = (over: object = {}) => ({
  location_id: 1, location: 'Main Kitchen',
  checklists: { due: 10, on_time: 8, percent: 80 },
  monitoring: { done: 18, due: 20, missed: 2, failed: 3, percent: 90 },
  ccp: { done: 4, due: 5, missed: 1, failed: 2, percent: 80 },
  failed_readings: 3, open_actions: 1, overdue_now: 4,
  probes: { total: 2, needs_calibration: 1, due_soon: 1 },
  missed_by_hour: { monitoring: hours({ 6: 2 }), tasks: hours({ 14: 1, 15: 3 }) },
  ...over,
})

describe('CompliancePanel', () => {
  beforeEach(() => { mocks.paths = []; mocks.data = null })

  it('shows each outlet with its on-time percentages, CCP checks apart, failures and what is open now', () => {
    mocks.data = { range: { date_from: '2026-02-24', date_to: '2026-03-02' }, sections: ['checklists', 'monitoring'], outlets: [outlet(), outlet({ location_id: 2, location: 'Rooftop Bar' })] }
    render(<CompliancePanel locationId={null} />)
    const card = screen.getByText('Main Kitchen').closest('div')!.parentElement!
    expect(within(card).getByText('Tasks on time (8 of 10)')).toBeTruthy()
    expect(within(card).getByText('Critical (CCP) checks on time (4 of 5)')).toBeTruthy()
    expect(within(card).getByText('Failed readings (2 critical)')).toBeTruthy()
    expect(within(card).getByText('Open corrective actions')).toBeTruthy()
    expect(within(card).getByText('Overdue now')).toBeTruthy()
    expect(within(card).getByText('Probes needing calibration (1 more due soon)')).toBeTruthy()
    expect(screen.getByText('Rooftop Bar')).toBeTruthy()
  })

  it('leaves out a part the viewer may not open and the CCP tile when there are no CCP checks', () => {
    mocks.data = { range: { date_from: 'a', date_to: 'b' }, sections: ['checklists'], outlets: [outlet({
      monitoring: null, ccp: null, failed_readings: null, open_actions: null, probes: null, missed_by_hour: { monitoring: hours({}), tasks: hours({}) } })] }
    render(<CompliancePanel locationId={null} />)
    expect(screen.getByText('Tasks on time (8 of 10)')).toBeTruthy()
    expect(screen.queryByText(/Checks recorded on time/)).toBeNull()
    expect(screen.queryByText(/Critical \(CCP\)/)).toBeNull()
    expect(screen.queryByText('Failed readings')).toBeNull()
    expect(screen.queryByText(/Monitoring checks missed/)).toBeNull()
    expect(screen.getByText(/Tasks not done on time/)).toBeTruthy()
  })

  it('shows n/a rather than 0% when nothing was due, and asks for the chosen period and outlet', () => {
    mocks.data = { range: { date_from: 'a', date_to: 'b' }, sections: ['checklists', 'monitoring'], outlets: [outlet({
      checklists: { due: 0, on_time: 0, percent: null }, ccp: { done: 0, due: 0, missed: 0, failed: 0, percent: null } })] }
    render(<CompliancePanel locationId={3} />)
    expect(screen.getByText('Tasks on time (0 of 0)')).toBeTruthy()
    expect(screen.getAllByText('n/a').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Critical \(CCP\)/)).toBeNull()
    expect(mocks.paths.at(-1)).toBe('/dashboard/compliance?days=7&location_id=3')
    fireEvent.change(screen.getByLabelText('Compliance period'), { target: { value: '30' } })
    expect(mocks.paths.at(-1)).toBe('/dashboard/compliance?days=30&location_id=3')
  })
})

describe('MissedByHour', () => {
  it('puts the count in each hour box and says in words when work slips most', () => {
    render(<MissedByHour title="Checks missed" hours={hours({ 6: 2, 7: 2, 9: 1 })} />)
    expect(screen.getByText('5 missed, most at 06:00 and 07:00')).toBeTruthy()
    expect(screen.getByLabelText(/Checks missed by hour of the day: 5 missed/)).toBeTruthy()
    expect(screen.getAllByRole('listitem')).toHaveLength(24)
    expect(screen.getByTitle('09:00: 1 missed').textContent).toContain('1')
  })

  it('says none were missed when the day was clean', () => {
    render(<MissedByHour title="Checks missed" hours={hours({})} />)
    expect(screen.getByText('none missed')).toBeTruthy()
  })
})

describe('LimitTrend', () => {
  const point = (hour: number, value: number, passed = true, warning = false) => ({ recorded_at: `2026-03-02T${String(hour).padStart(2, '0')}:00:00Z`, value, passed, warning })

  it('draws the limits and amber levels, marks a failed reading with a cross and counts failures in words', () => {
    const { container } = render(<LimitTrend points={[point(1, 60), point(2, 20, false), point(3, 64, true, true)]} min={55} max={65} warnMax={63} unit="°C" />)
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('3 readings')
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('1 outside the limits')
    expect(container.querySelectorAll('line[stroke-dasharray]')).toHaveLength(3)  // highest, lowest, amber from
    expect(container.querySelectorAll('circle')).toHaveLength(2)
    expect(container.querySelectorAll('path')).toHaveLength(1)  // the cross
    expect(screen.getByText(/Highest allowed 65 °C/)).toBeTruthy()
    expect(screen.getByText(/Amber from 63 °C/)).toBeTruthy()
    expect(screen.getByText(/Failed reading: 1/)).toBeTruthy()
  })

  it('copes with one reading, no limits, and no readings at all', () => {
    const one = render(<LimitTrend points={[point(1, 5)]} min={null} max={null} />)
    expect(one.container.querySelectorAll('circle')).toHaveLength(1)
    one.unmount()
    render(<LimitTrend points={[]} min={55} max={65} />)
    expect(screen.getByText('No readings in this period.')).toBeTruthy()
  })
})
