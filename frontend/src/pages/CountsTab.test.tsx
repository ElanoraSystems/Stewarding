import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CountsTab } from '@/pages/CountsTab'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: mocks.api }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => (await action(), true) }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { permissions: ['inventory.count'], locations: [{ id: 1, name: 'Main Kitchen' }] } }) }))
vi.mock('@/components/WorkLocationSelect', () => ({
  WorkLocationSelect: ({ onChange }: { onChange: (id: number | null) => void }) => <button type="button" onClick={() => onChange(1)}>Pick the kitchen</button>,
}))
vi.mock('@/lib/useItems', () => {
  const items = [
    { id: 1, code: 'PL-001', name: 'Dinner plate', category: 'Plates', unit: 'Each', storage_location: 'Shelf A' },
    { id: 2, code: 'PL-002', name: 'Side plate', category: 'Plates', unit: 'Each', storage_location: 'Shelf A' },
    { id: 3, code: 'KN-001', name: 'Chef knife', category: 'Knives', unit: 'Each', storage_location: 'Drawer 1' },
    { id: 4, code: 'XX-001', name: 'Never here', category: 'Knives', unit: 'Each', storage_location: null },
  ]
  return { useAllItems: () => ({ items, byId: new Map(items.map((i) => [i.id, i])) }) }
})
vi.mock('@/lib/useApi', () => ({
  qs: (p: Record<string, unknown>) => `?${Object.entries(p).map(([k, v]) => `${k}=${v}`).join('&')}`,
  useApi: (path: string | null) => ({
    reload: () => undefined,
    data: path?.startsWith('/stock/count-limits') ? [
      { item_id: 1, received: 50, system_qty: 40, invoices: 50, opening: 0, transfers_in: 0 },
      { item_id: 2, received: 20, system_qty: 20, invoices: 20, opening: 0, transfers_in: 0 },
      { item_id: 3, received: 5, system_qty: 5, invoices: 5, opening: 0, transfers_in: 0 },
      { item_id: 4, received: 0, system_qty: 0, invoices: 0, opening: 0, transfers_in: 0 },
    ] : path?.startsWith('/stock/counts') ? [] : null,
  }),
}))

describe('CountsTab', () => {
  beforeEach(() => {
    mocks.api.mockReset()
    mocks.api.mockImplementation(async (path: string) => (path.startsWith('/stock/count-draft') ? { entries: { '3': { qty: '4', reason: '' } }, updated_at: '2026-03-02T08:00:00Z' } : {}))
  })

  it('brings back the count in progress, hides items not held here, and filters by search and category', async () => {
    const user = userEvent.setup()
    render(<CountsTab />)
    await user.click(screen.getByRole('button', { name: 'Pick the kitchen' }))
    expect((await screen.findByLabelText('Counted Chef knife') as HTMLInputElement).value).toBe('4')     // restored from the saved draft
    expect(screen.queryByLabelText('Counted Never here')).toBeNull()                                       // nothing was ever received here
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Plates' } })
    expect(screen.queryByLabelText('Counted Chef knife')).toBeNull()
    await user.type(screen.getByLabelText('Search items'), 'side')
    expect(screen.getByLabelText('Counted Side plate')).toBeTruthy()
    expect(screen.queryByLabelText('Counted Dinner plate')).toBeNull()
  })

  it('saves what is typed as a draft after a short pause', async () => {
    const user = userEvent.setup()
    render(<CountsTab />)
    await user.click(screen.getByRole('button', { name: 'Pick the kitchen' }))
    await screen.findByLabelText('Counted Dinner plate')
    await user.type(screen.getByLabelText('Counted Dinner plate'), '37')
    await waitFor(() => expect(mocks.api).toHaveBeenCalledWith('/stock/count-draft', expect.objectContaining({ method: 'PUT',
      body: { location_id: 1, entries: expect.objectContaining({ 1: { qty: '37', reason: '' } }) } })), { timeout: 3000 })
  })
})
