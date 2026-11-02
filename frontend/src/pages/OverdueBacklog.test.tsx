import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { OverdueBacklog } from '@/pages/OverdueBacklog'
import type { Instance } from '@/pages/ChecklistTaskCard'

const task = (id: number, day: string, template_name: string) => ({ id, local_date: day, template_name, description: `Task ${id}`, effective_status: 'overdue' }) as Instance

describe('OverdueBacklog', () => {
  const items = [task(1, '2026-10-29', 'Daily'), task(2, '2026-10-29', 'Weekly'), task(3, '2026-10-31', 'Daily')]

  it('lists the overdue days newest first with their counts, and opens a day on request', async () => {
    const user = userEvent.setup()
    render(<OverdueBacklog items={items} total={3} canWaive onWaiveDay={() => {}} renderDay={(_, tasks) => <p>{tasks.map((t) => t.description).join(', ')}</p>} />)
    const days = screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'))
    expect(days).toEqual(['31 Oct 2026', '29 Oct 2026'])
    expect(screen.getByText('3 overdue tasks')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: '29 Oct 2026' })).getByText('2 overdue')).toBeTruthy()
    const button = within(screen.getByRole('region', { name: '29 Oct 2026' })).getAllByRole('button')[0]
    expect(button.getAttribute('aria-expanded')).toBe('false')
    await user.click(button)
    expect(button.getAttribute('aria-expanded')).toBe('true')
  })

  it('waives a whole day in one go, only for people allowed to', async () => {
    const user = userEvent.setup()
    const onWaiveDay = vi.fn()
    const { unmount } = render(<OverdueBacklog items={items} total={3} canWaive onWaiveDay={onWaiveDay} renderDay={() => null} />)
    await user.click(screen.getByRole('button', { name: 'Waive all 2' }))
    expect(onWaiveDay).toHaveBeenCalledWith([1, 2], '2026-10-29')
    unmount()
    render(<OverdueBacklog items={items} total={3} canWaive={false} onWaiveDay={onWaiveDay} renderDay={() => null} />)
    expect(screen.queryByRole('button', { name: /Waive all/ })).toBeNull()
  })
})
