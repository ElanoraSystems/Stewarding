import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ChecklistConfig } from '@/pages/ChecklistConfig'

const task = (id: number, description: string) => ({ id, template_id: 1, description, instructions: null, shift_id: null, assigned_role: null, assigned_employee_id: null, scheduled_time: null, deadline_time: null,
  weekdays: '0,1,2,3,4,5,6', priority: 'normal', requires_photo: false, requires_reading: false, requires_verification: false, mandatory_for_checkout: false, escalation_minutes: null, active_from: null, active_to: null, active: true })
const templates = [
  { id: 1, name: 'Opening', category: 'Operational', location_id: 2, frequency: 'daily', active: true, visible_to: null, tasks: [task(1, 'Unlock kitchen'), task(2, 'Switch on lights')] },
  { id: 2, name: 'Closing', category: 'Operational', location_id: 2, frequency: 'daily', active: true, visible_to: null, tasks: [task(3, 'Lock up')] },
]

vi.mock('@/lib/api', () => ({ api: vi.fn() }))
vi.mock('@/lib/toast', () => ({ useRun: () => async () => true }))
vi.mock('@/lib/useLookups', () => ({ useLookup: () => ['Operational'] }))
vi.mock('@/lib/useApi', () => ({ qs: () => '', useApi: () => ({ data: templates, reload: () => undefined }) }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { locations: [{ id: 2, name: 'Beach Kitchen' }], permissions: [] } }) }))

describe('ChecklistConfig', () => {
  it('starts every checklist closed, with its task count, and opens one on request', async () => {
    const user = userEvent.setup()
    render(<ChecklistConfig locationId={2} onLocation={() => {}} />)
    const opening = screen.getByRole('region', { name: 'Opening' })
    const toggle = within(opening).getAllByRole('button')[0]
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(within(opening).getByText('2 tasks')).toBeTruthy()
    await user.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    await user.click(screen.getByRole('button', { name: 'Close all' }))
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    await user.click(screen.getByRole('button', { name: 'Open all' }))
    expect(within(screen.getByRole('region', { name: 'Closing' })).getAllByRole('button')[0].getAttribute('aria-expanded')).toBe('true')
  })
})
