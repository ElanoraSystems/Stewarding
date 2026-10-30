import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OpeningDateModal } from '@/pages/OpeningDateModal'

const call = vi.fn().mockResolvedValue({})
vi.mock('@/lib/api', () => ({ api: (...a: unknown[]) => call(...a) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (f: () => Promise<unknown>) => { await f(); return true } }))

describe('OpeningDateModal', () => {
  it('needs a date and a reason, then sends the new date for that line', async () => {
    const onDone = vi.fn()
    render(<OpeningDateModal txn={{ id: 9, occurred_at: '2026-10-28T20:45:00Z' }} onClose={() => {}} onDone={onDone} />)
    const button = screen.getByRole('button', { name: 'Change the date' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('New date'), { target: { value: '2026-09-30' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Belongs to September' } })
    fireEvent.click(button)
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(call).toHaveBeenCalledWith('/inventory/transactions/9/date', { method: 'PUT', body: { new_date: '2026-09-30', reason: 'Belongs to September' } })
  })
})
