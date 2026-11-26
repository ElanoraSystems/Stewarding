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
    expect(within(logs).getByText('1 failed')).toBeTruthy()
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

  it('folds many tasks of one checklist into one group and approves them together', async () => {
    const user = userEvent.setup()
    const task = (id: number) => ({ id, description: `Task ${id}`, checklist: 'Opening', location_id: 2, local_date: '2026-11-01', done_by: 'Sid', done_at: '2026-11-01T10:00:00Z', comment: null, has_photo: false })
    render(<ApprovalsTab data={{ tasks: [1, 2, 3, 4, 5].map(task), readings: [], count: 5 }} loading={false} reload={() => {}} />)
    expect(screen.queryByText('Task 1')).toBeNull()  // five tasks start folded
    await user.click(screen.getByRole('button', { name: /Opening/ }))
    expect(screen.getByText('Task 1')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Approve all' }))
    await user.click(screen.getAllByRole('button', { name: 'Approve' }).at(-1)!)
    expect(mocks.api).toHaveBeenCalledWith('/checklists/instances/verify-many', { body: { instance_ids: [1, 2, 3, 4, 5], comment: null } })
  })

  it('shows one row per visit with every reading as a chip, and can pick only the passed ones', async () => {
    const user = userEvent.setup()
    const read = (id: number, stage: string, passed: boolean, at: string) => ({ id, equipment: 'Cooking log', stage, value: passed ? 'OK' : 'Bad', passed, location_id: 2, done_by: 'Maya', done_at: at, comment: null })
    const data: Waiting = { tasks: [], count: 4, readings: [read(1, 'Temp', true, '2026-11-01T08:00:00Z'), read(2, 'Method', false, '2026-11-01T08:01:00Z'), read(3, 'Temp', true, '2026-11-01T18:00:00Z')] }
    render(<ApprovalsTab data={data} loading={false} reload={() => {}} />)
    const logs = within(screen.getByRole('region', { name: 'Monitoring logs' }))
    expect(logs.getAllByRole('listitem')).toHaveLength(2)  // the morning visit and the evening visit
    expect(logs.getByText('Method: Bad')).toBeTruthy()
    await user.click(logs.getByRole('button', { name: /Select all passed \(2\)/ }))
    expect(logs.getByRole('button', { name: /Approve or reject selected \(2\)/ })).toBeTruthy()
  })

  it('keeps the late tag and the reason on a grouped task', () => {
    const late = { ...waiting.tasks[0], late_minutes: 45, late_reason: 'Short staffed' }
    render(<ApprovalsTab data={{ tasks: [late], readings: [], count: 1 }} loading={false} reload={() => {}} />)
    expect(screen.getByText(/Late by/)).toBeTruthy()
    expect(screen.getByText(/Short staffed/)).toBeTruthy()
  })

  it('puts a failed visit first, then a CCP, and labels the level', () => {
    const read = (id: number, equipment: string, passed: boolean, control: string) => ({ id, equipment, stage: 'Temp', value: '3 °C', passed, location_id: 2, done_by: 'Maya', done_at: `2026-11-01T0${id}:00:00Z`, comment: null, control })
    const data: Waiting = { tasks: [], count: 3, readings: [read(1, 'Plain fridge', true, 'prp'), read(2, 'Chiller CCP', true, 'ccp'), read(3, 'Failed oprp', false, 'oprp')] }
    render(<ApprovalsTab data={data} loading={false} reload={() => {}} />)
    const rows = within(screen.getByRole('region', { name: 'Monitoring logs' })).getAllByRole('listitem').map((li) => li.textContent ?? '')
    expect(rows[0]).toContain('Failed oprp')
    expect(rows[1]).toContain('Chiller CCP')
    expect(rows[1]).toContain('CCP')
    expect(rows[2]).toContain('Plain fridge')
  })

  it('says so when nothing is waiting', () => {
    render(<ApprovalsTab data={{ tasks: [], readings: [], count: 0 }} loading={false} reload={() => {}} />)
    expect(screen.getByText('Nothing is waiting for your approval')).toBeTruthy()
  })
})
