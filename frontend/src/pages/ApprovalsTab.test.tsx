import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApprovalsTab, type Waiting } from '@/pages/ApprovalsTab'

const mocks = vi.hoisted(() => ({ api: vi.fn(async (_path: string, _options?: unknown) => ({}) as unknown) }))
vi.mock('@/lib/api', () => ({ api: mocks.api }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { locations: [{ id: 2, name: 'Beach Kitchen' }] } }) }))
vi.mock('@/lib/toast', () => ({ useToast: () => vi.fn() }))

const waiting: Waiting = {
  count: 3,
  tasks: [{ id: 5, description: 'Clean drains', checklist: 'Daily', location_id: 2, local_date: '2026-11-01', done_by: 'Sid', done_at: '2026-11-01T10:00:00Z', comment: null, has_photo: false }],
  readings: [{ id: 9, equipment: 'Chiller #25', stage: 'Morning temperature', value: '3 °C', passed: true, location_id: 2, done_by: 'Maya', done_at: '2026-11-01T08:00:00Z', comment: null },
    { id: 10, equipment: 'Chiller #48', stage: 'Morning temperature', value: '9 °C', passed: false, location_id: 2, done_by: 'Maya', done_at: '2026-11-01T08:05:00Z', comment: null }],
}

describe('ApprovalsTab', () => {
  beforeEach(() => mocks.api.mockClear())

  it('lists the tasks and logs waiting, and approves a task with a comment', async () => {
    const user = userEvent.setup()
    render(<ApprovalsTab data={waiting} loading={false} reload={() => {}} />)
    expect(screen.getByRole('region', { name: 'Checklist tasks' })).toBeTruthy()
    const logs = screen.getByRole('region', { name: 'Monitoring logs' })
    expect(within(logs).getByText('Fail')).toBeTruthy()
    await user.click(within(screen.getByRole('region', { name: 'Checklist tasks' })).getByRole('button', { name: 'Approve' }))
    await user.type(screen.getByLabelText(/Comment/), 'Well done')
    await user.click(screen.getAllByRole('button', { name: 'Approve' }).at(-1)!)
    expect(mocks.api).toHaveBeenCalledWith('/checklists/instances/verify-many', { body: { instance_ids: [5], comment: 'Well done' } })
  })

  it('rejects the selected logs with a reason', async () => {
    const user = userEvent.setup()
    render(<ApprovalsTab data={waiting} loading={false} reload={() => {}} />)
    const logs = within(screen.getByRole('region', { name: 'Monitoring logs' }))
    await user.click(logs.getByRole('button', { name: 'Select all' }))
    await user.click(logs.getByRole('button', { name: /Approve or reject selected \(2\)/ }))
    await user.click(screen.getByRole('radio', { name: 'Reject' }))
    await user.type(screen.getByLabelText(/Why are you rejecting/), 'Wrong probe')
    await user.click(screen.getAllByRole('button', { name: 'Reject' }).filter((b) => b.getAttribute('role') !== 'radio').at(-1)!)  // the dialog's own button comes last
    expect(mocks.api).toHaveBeenCalledWith('/monitoring/readings/reject', { body: { reading_ids: [9, 10], reason: 'Wrong probe' } })
  })

  it('says so when nothing is waiting', () => {
    render(<ApprovalsTab data={{ tasks: [], readings: [], count: 0 }} loading={false} reload={() => {}} />)
    expect(screen.getByText('Nothing is waiting for your approval')).toBeTruthy()
  })
})
