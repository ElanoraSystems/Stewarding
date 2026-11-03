import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { TasksPage } from '@/pages/TasksPage'

const mocks = vi.hoisted(() => ({ permissions: [] as string[] }))
const alert = { id: 1, kind: 'check_overdue', title: 'Check overdue: Chiller #25', body: null, priority: 'high', location_id: 2, link: '/monitoring', created_at: '2026-11-01T10:00:00Z', read_at: null, requires_ack: true, acknowledged_at: null, action_needed: true }

vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { id: 1, permissions: mocks.permissions, locations: [{ id: 2, name: 'Beach Kitchen' }], tier: 'steward' } }) }))
vi.mock('@/lib/api', () => ({ api: vi.fn(async () => ({})) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async () => true, useToast: () => vi.fn() }))
vi.mock('@/components/PushToggle', () => ({ PushToggle: () => null }))
vi.mock('@/lib/useApi', () => ({
  qs: () => '',
  useApi: (path: string | null) => ({ reload: () => undefined, loading: false, data: path?.startsWith('/notifications') ? { total: 1, unread: 1, items: [alert] } : { total: 0, items: [] } }),
}))

describe('alerts on the Tasks page', () => {
  it('offers Approve and Reject only to people who approve work', () => {
    mocks.permissions = ['notification.view', 'checklist.complete']
    const { unmount } = render(<MemoryRouter><TasksPage /></MemoryRouter>)
    expect(screen.getByText('Check overdue: Chiller #25')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    unmount()
    mocks.permissions = ['notification.view', 'temp.review']
    render(<MemoryRouter><TasksPage /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Approve' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeTruthy()
  })
})
