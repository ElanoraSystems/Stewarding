import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NotificationRoutes } from '@/pages/settings/NotificationRoutes'

const mocks = vi.hoisted(() => ({ api: vi.fn(async (_path: string, _options?: unknown) => ({}) as unknown) }))
const routes = {
  categories: [{ key: 'attendance', label: 'Attendance', about: 'No check-in', default: 'Managers and supervisors' }],
  roles: [{ name: 'manager', label: 'Back of House Manager', tier: 'manager' }, { name: 'head_chef', label: 'Head Chef', tier: 'supervisor' }],
  routes: { attendance: null },
}
vi.mock('@/lib/api', () => ({ api: mocks.api }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true } }))
vi.mock('@/lib/useApi', () => ({ useApi: () => ({ data: routes, reload: () => undefined }) }))

describe('NotificationRoutes', () => {
  beforeEach(() => mocks.api.mockClear())

  it('shows the default, and saves the roles chosen for a kind of alert', async () => {
    const user = userEvent.setup()
    render(<NotificationRoutes />)
    expect(screen.getByText('Default: Managers and supervisors')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Back of House Manager' }))
    expect(screen.getByText('Told: Back of House Manager')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.api).toHaveBeenCalledWith('/settings/notification-routes', { method: 'PUT', body: { routes: { attendance: ['manager'] } } })
  })
})
