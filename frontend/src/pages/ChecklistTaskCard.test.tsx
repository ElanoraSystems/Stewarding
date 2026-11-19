import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChecklistTaskCard, type Instance } from '@/pages/ChecklistTaskCard'

const mocks = vi.hoisted(() => ({ calls: [] as { path: string; body: unknown }[] }))

vi.mock('@/lib/api', () => ({ api: vi.fn(async (path: string, init: { body: unknown }) => { mocks.calls.push({ path, body: init.body }); return {} }), uploadFile: vi.fn() }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { id: 1, permissions: ['checklist.complete'] } }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true } }))

const task = (extra: Partial<Instance>) => ({
  id: 7, task_id: 3, location_id: 1, local_date: '2026-11-01', status: 'in_progress', effective_status: 'overdue', due_at: '2026-11-01T09:00:00Z', assigned_employee_id: null,
  completed_by: null, comment: null, description: 'Clean drains', instructions: null, priority: 'normal', requires_photo: false, requires_reading: false,
  requires_verification: false, category: 'Safety', frequency: 'daily', waive_reason: null, ...extra,
}) as Instance

describe('ChecklistTaskCard late tasks', () => {
  beforeEach(() => { mocks.calls.length = 0 })

  it('asks why an overdue task is late and will not submit without a reason', async () => {
    const user = userEvent.setup()
    render(<ChecklistTaskCard item={task({})} staff={[]} onChanged={() => undefined} timezone="UTC" />)
    await user.click(screen.getByRole('button', { name: /Complete/ }))
    const submit = screen.getByRole('button', { name: 'Submit' }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    await user.type(screen.getByLabelText(/Why is it late/), 'abc')
    expect(submit.disabled).toBe(true)
    await user.type(screen.getByLabelText(/Why is it late/), 'de')
    expect(submit.disabled).toBe(false)
    await user.click(submit)
    expect(mocks.calls[0].path).toBe('/checklists/instances/7/complete')
    expect((mocks.calls[0].body as { late_reason: string }).late_reason).toBe('abcde')
  })

  it('does not ask a task that is not overdue for a reason', async () => {
    const user = userEvent.setup()
    render(<ChecklistTaskCard item={task({ effective_status: 'in_progress' })} staff={[]} onChanged={() => undefined} timezone="UTC" />)
    await user.click(screen.getByRole('button', { name: /Complete/ }))
    expect(screen.queryByLabelText(/Why is it late/)).toBeNull()
    expect((screen.getByRole('button', { name: 'Submit' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('tags a task completed late with how late it was and why', () => {
    render(<ChecklistTaskCard item={task({ status: 'verified', effective_status: 'verified', late_minutes: 75, late_reason: 'Delivery kept the team busy' })} staff={[]} onChanged={() => undefined} timezone="UTC" />)
    expect(screen.getByText('Late by 1 h 15 min')).toBeTruthy()
    expect(screen.getByText(/Delivery kept the team busy/)).toBeTruthy()
  })
})
