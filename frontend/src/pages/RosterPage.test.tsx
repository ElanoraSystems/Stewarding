import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { iso } from '@/lib/dates'
import { RosterPage } from '@/pages/RosterPage'

const day = (offset: number) => { const d = new Date(); d.setDate(d.getDate() + offset); return iso(d) }
const row = (id: number, employee_id: number, shift_id: number, valid_from: string, valid_to: string | null) => ({ id, employee_id, shift_id, weekday: 0, valid_from, valid_to, cycle_weeks: 1, cycle_week: 0 })

const data = vi.hoisted(() => ({ assignments: [] as unknown[] }))
data.assignments = [
  row(1, 1, 1, '2026-01-05', null),            // running, no end
  row(2, 2, 2, '2026-01-05', 'FUTURE'),        // running, ends later
  row(3, 3, 1, '2026-01-05', 'TODAY'),         // ended today (End was clicked)
  row(4, 4, 2, '2026-01-05', 'PAST'),          // ended earlier
  row(5, 5, 1, 'SOON', null),                  // not started
]

vi.mock('@/lib/api', () => ({ api: vi.fn(async () => ({})) }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { permissions: ['roster.manage'] } }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true } }))
vi.mock('@/components/LocationSelect', () => ({ LocationSelect: () => null }))
vi.mock('@/lib/useApi', () => ({
  qs: () => '',
  useApi: (path: string | null) => {
    if (!path) return { data: null, reload: () => undefined }
    if (path.startsWith('/roster/shifts')) return { data: [{ id: 1, name: 'Morning', start_time: '06:00:00', end_time: '14:00:00', grace_minutes: 10, kind: 'work', active: true }, { id: 2, name: 'Evening', start_time: '14:00:00', end_time: '22:00:00', grace_minutes: 10, kind: 'work', active: true }], reload: () => undefined }
    if (path.startsWith('/roster/assignments')) {
      const fix = (a: { valid_from: string; valid_to: string | null }) => ({ ...a, valid_from: a.valid_from === 'SOON' ? day(5) : a.valid_from, valid_to: a.valid_to === 'FUTURE' ? day(3) : a.valid_to === 'TODAY' ? day(0) : a.valid_to === 'PAST' ? day(-10) : a.valid_to })
      return { data: (data.assignments as { valid_from: string; valid_to: string | null }[]).map(fix), reload: () => undefined }
    }
    if (path.startsWith('/employees')) return { data: { items: [1, 2, 3, 4, 5].map((id) => ({ id, full_name: `Person ${id}` })) }, reload: () => undefined }
    return { data: [], reload: () => undefined }
  },
}))

describe('RosterPage weekly assignments', () => {
  it('shows only the running assignments first, under their shift, and moves finished ones to Ended', async () => {
    const user = userEvent.setup()
    render(<RosterPage />)
    const tabs = screen.getByRole('tablist', { name: 'Which assignments' })
    expect(within(tabs).getByRole('tab', { name: /Active \(2\)/ })).toBeTruthy()
    expect(within(tabs).getByRole('tab', { name: /Starting soon \(1\)/ })).toBeTruthy()
    expect(within(tabs).getByRole('tab', { name: /Ended \(2\)/ })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Morning' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Evening' })).toBeTruthy()
    expect(screen.getByText('Person 1')).toBeTruthy()
    expect(screen.getByText('Person 2')).toBeTruthy()
    expect(screen.queryByText('Person 3')).toBeNull()  // clicked End today, so it is in history
    expect(screen.queryByText('Person 4')).toBeNull()
    expect(screen.queryByText('Person 5')).toBeNull()

    await user.click(within(tabs).getByRole('tab', { name: /Ended/ }))
    const ended = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent).filter((t) => t?.startsWith('Person'))
    expect(ended).toEqual(['Person 3', 'Person 4'])  // the most recently ended first
    expect(screen.queryByRole('button', { name: 'End' })).toBeNull()  // an ended assignment cannot be ended again

    await user.click(within(tabs).getByRole('tab', { name: /Starting soon/ }))
    expect(screen.getByText('Person 5')).toBeTruthy()
    expect(screen.getByText('Starts in 5 days')).toBeTruthy()
  })
})
