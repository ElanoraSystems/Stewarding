import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '@/lib/toast'
import { RecallTab } from '@/pages/trace/RecallTab'

vi.mock('@/lib/useApi', () => ({
  useApi: (path: string | null) => {
    if (path?.startsWith('/lots/by-code/')) return { data: { id: 7, code: 'B1' }, loading: false, error: null, reload: () => undefined }
    if (path === '/lots/7/recall') return {
      data: { title: 'Lot Recall Trace - B1', period: { label: 'Traced now' }, locations: ['Main'], groups: [{ title: 'Lot B1 - summary', meta: [], columns: [['received', 'Received'], ['failed', 'Failed checks']], rows: [{ received: '10 kg', failed: 1 }], totals: [] }] },
      loading: false, error: null, reload: () => undefined,
    }
    return { data: null, loading: false, error: null, reload: () => undefined }
  },
}))

describe('RecallTab', () => {
  afterEach(() => vi.restoreAllMocks())

  it('asks for a lot code, then shows the trace with download buttons', async () => {
    render(<ToastProvider><RecallTab /></ToastProvider>)
    expect(screen.getByRole('button', { name: 'Show trace' }).hasAttribute('disabled')).toBe(true)
    expect(screen.queryByRole('button', { name: /PDF/ })).toBeNull()
    await userEvent.setup().type(screen.getByLabelText('Lot code'), 'B1{Enter}')
    await waitFor(() => expect(screen.getByText('Lot B1 - summary')).toBeTruthy())
    expect(screen.getByRole('button', { name: /PDF/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Excel/ })).toBeTruthy()
  })
})
