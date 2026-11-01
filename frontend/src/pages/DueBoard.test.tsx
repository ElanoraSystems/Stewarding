import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DueBoard, type DueCard } from '@/pages/DueBoard'

const card = (equipment_id: number, equipment: string, hour: number, status: DueCard['status'], stage = 'Temperature'): [string, DueCard] => [
  `${equipment_id}-${hour}`,
  { stages: [stage], status, closed: false, first: { equipment_id, equipment, schedule_id: equipment_id * 100 + hour, stage, slot_at: `2026-11-01T${String(hour).padStart(2, '0')}:00:00Z`, opens_at: `2026-11-01T${String(hour - 1).padStart(2, '0')}:30:00Z`, open: true, status } },
]

describe('DueBoard', () => {
  it('puts a point checked twice a day on one row with its times in order, under its kind, points in natural order', () => {
    const cards = [card(2, 'Chiller #25', 18, 'upcoming'), card(1, 'Chiller #9', 9, 'done'), card(2, 'Chiller #25', 9, 'done'), card(3, 'Wash', 9, 'due', 'Wash')]
    render(<DueBoard cards={cards} kindOf={new Map([[1, 'Cold storage'], [2, 'Cold storage'], [3, 'Dishwasher']])} timezone="UTC" canRecord onStart={() => {}} />)
    expect(screen.getByRole('region', { name: 'Cold storage' })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Dishwasher' })).toBeTruthy()
    const rows = within(screen.getByRole('region', { name: 'Cold storage' })).getAllByRole('listitem')
    expect(rows.map((r) => r.querySelector('span')?.textContent)).toEqual(['Chiller #9', 'Chiller #25'])  // 9 before 25, not by letters
    const times = within(rows[1]).getAllByRole('button').map((b) => b.getAttribute('aria-label') ?? '')
    expect(times[0]).toContain('09:00')
    expect(times[1]).toContain('18:00')
    expect(screen.getByText(/2 of 4/)).toBeTruthy()
  })

  it('starts the check when a due time is pressed, and hides what is done on request', async () => {
    const onStart = vi.fn()
    const user = userEvent.setup()
    render(<DueBoard cards={[card(1, 'Chiller #25', 9, 'done'), card(1, 'Chiller #25', 18, 'due')]} kindOf={new Map([[1, 'Cold storage']])} timezone="UTC" canRecord onStart={onStart} />)
    expect((screen.getByRole('button', { name: /09:00.*recorded/ }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(screen.getByRole('button', { name: /18:00/ }))
    expect(onStart).toHaveBeenCalledWith(1, 118)
    await user.click(screen.getByLabelText('Only what still needs doing'))
    expect(screen.queryByRole('button', { name: /09:00/ })).toBeNull()
  })
})
