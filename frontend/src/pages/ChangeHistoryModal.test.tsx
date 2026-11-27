import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChangeHistoryModal } from '@/pages/ChangeHistoryModal'

const mocks = vi.hoisted(() => ({ data: null as unknown, paths: [] as string[] }))
vi.mock('@/lib/useApi', async (original) => ({ ...(await original<typeof import('@/lib/useApi')>()), useApi: (path: string) => { mocks.paths.push(path); return { data: mocks.data, loading: false, error: null, reload: vi.fn() } } }))

describe('ChangeHistoryModal', () => {
  it('shows who changed what, when, and from what to what', () => {
    mocks.data = [
      { when: '2026-11-27T10:00:00Z', by: 'Ashfaque', what: 'Changed a task', subject: 'Clean drains', changes: [{ field: 'Priority', from: 'normal', to: 'high' }] },
      { when: '2026-11-01T10:00:00Z', by: 'Ashfaque', what: 'Added a task', subject: 'Clean drains', changes: [{ field: 'Description', from: null, to: 'Clean drains' }] },
    ]
    render(<ChangeHistoryModal title="Change history: Closing" path="/checklists/templates/4/history" onClose={() => undefined} />)
    expect(mocks.paths).toContain('/checklists/templates/4/history')
    const first = screen.getByText('Changed a task', { exact: false }).closest('li')!
    expect(within(first).getByText(/normal/)).toBeTruthy()
    expect(within(first).getByText(/high/)).toBeTruthy()
    expect(screen.getByText('Added a task', { exact: false })).toBeTruthy()
  })

  it('says so when nothing was changed', () => {
    mocks.data = []
    render(<ChangeHistoryModal title="Change history" path="/equipment/1/history" onClose={() => undefined} />)
    expect(screen.getByText('No changes recorded.')).toBeTruthy()
  })
})
