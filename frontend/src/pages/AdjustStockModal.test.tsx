import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AdjustStockModal } from '@/pages/AdjustStockModal'

const post = vi.fn().mockResolvedValue({})
vi.mock('@/lib/api', () => ({ api: (...a: unknown[]) => post(...a) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (f: () => Promise<unknown>) => { await f(); return true } }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { locations: [{ id: 3, name: 'F&B Main Store' }] } }) }))
vi.mock('@/lib/useItems', () => ({ useAllItems: () => ({ items: [{ id: 7, code: 'CT-1', name: 'Cigar tray', unit: 'Each', by_location: { 3: 179 } }] }) }))

describe('AdjustStockModal', () => {
  it('turns the stock that should be held into the adjustment that corrects the books', async () => {
    const onDone = vi.fn()
    render(<AdjustStockModal open onClose={() => {}} onDone={onDone} />)
    const user = userEvent.setup()
    await user.type(screen.getByRole('combobox', { name: 'Item' }), 'cigar')
    await user.click(screen.getByRole('option', { name: /Cigar tray/ }))
    fireEvent.change(screen.getByLabelText('Stock should be'), { target: { value: '0' } })
    expect(screen.getByText(/The books hold 179 here now. This posts -179/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Entered by mistake' } })
    fireEvent.click(screen.getByRole('button', { name: 'Post the adjustment' }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(post).toHaveBeenCalledWith('/inventory/transactions', { body: { item_id: 7, location_id: 3, txn_type: 'adjustment', qty: -179, reason: 'Entered by mistake' } })
  })
})
