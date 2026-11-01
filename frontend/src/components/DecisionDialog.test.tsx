import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DecisionDialog } from '@/components/DecisionDialog'

describe('DecisionDialog', () => {
  it('approves with or without a comment, and will not reject without a reason', async () => {
    const user = userEvent.setup()
    const onDecide = vi.fn().mockResolvedValue(true)
    render(<DecisionDialog open title="Approve or reject" subject="Clean drains" onClose={() => {}} onDecide={onDecide} />)
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onDecide).toHaveBeenLastCalledWith('approved', '')
    await user.click(screen.getByRole('radio', { name: 'Reject' }))
    const reject = screen.getAllByRole('button', { name: 'Reject' }).find((b) => b.getAttribute('role') !== 'radio') as HTMLButtonElement
    expect(reject.disabled).toBe(true)
    await user.type(screen.getByLabelText(/Why are you rejecting/), 'Still dirty')
    expect(reject.disabled).toBe(false)
    await user.click(reject)
    expect(onDecide).toHaveBeenLastCalledWith('rejected', 'Still dirty')
  })
})
