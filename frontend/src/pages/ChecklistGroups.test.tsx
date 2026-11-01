import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ChecklistGroups } from '@/pages/ChecklistGroups'
import type { Instance } from '@/pages/ChecklistTaskCard'

const task = (id: number, template_name: string, effective_status: string, hour: number, extra: Partial<Instance> = {}) =>
  ({ id, template_name, effective_status, description: `Task ${id}`, category: 'Safety', frequency: 'daily', due_at: `2026-11-01T${String(hour).padStart(2, '0')}:00:00Z`, ...extra }) as Instance

const render_ = (items: Instance[], props = {}) => render(<ChecklistGroups items={items} timezone="UTC" renderTask={(t) => <p key={t.id}>{t.description}</p>} {...props} />)

describe('ChecklistGroups', () => {
  const items = [task(1, 'Closing', 'not_started', 22), task(2, 'Opening', 'completed', 6), task(3, 'Opening', 'not_started', 7), task(4, 'Opening', 'overdue', 6), task(5, 'Closing', 'not_started', 23)]

  it('shows one section per checklist, the one to do first on top, all closed, each with its own progress', () => {
    render_(items)
    const sections = screen.getAllByRole('region')
    expect(sections.map((s) => s.getAttribute('aria-label'))).toEqual(['Opening', 'Closing'])
    const [opening, closing] = sections.map((s) => within(s).getAllByRole('button')[0])
    expect(opening.getAttribute('aria-expanded')).toBe('false')
    expect(closing.getAttribute('aria-expanded')).toBe('false')
    expect(within(sections[0]).getByText('1 of 3 done')).toBeTruthy()
    expect(within(sections[0]).getByText('1 overdue')).toBeTruthy()
    expect(within(sections[1]).getByText('0 of 2 done')).toBeTruthy()
    expect(within(sections[1]).getByText(/Next due 22:00/)).toBeTruthy()
  })

  it('opens a closed checklist when its heading is pressed, and opens or closes them all', async () => {
    const user = userEvent.setup()
    render_(items)
    const closing = () => within(screen.getByRole('region', { name: 'Closing' })).getAllByRole('button')[0]
    await user.click(closing())
    expect(closing().getAttribute('aria-expanded')).toBe('true')
    await user.click(screen.getByRole('button', { name: 'Close all' }))
    expect(closing().getAttribute('aria-expanded')).toBe('false')
    await user.click(screen.getByRole('button', { name: 'Open all' }))
    expect(closing().getAttribute('aria-expanded')).toBe('true')
  })

  it('puts the open tasks of a checklist before the finished ones, in time order', () => {
    render_(items)
    const opening = screen.getByRole('region', { name: 'Opening' })
    expect(within(opening).getAllByText(/^Task \d$/).map((p) => p.textContent)).toEqual(['Task 4', 'Task 3', 'Task 2'])
  })

  it('marks a finished checklist as all done and puts it last; with a filter set every checklist starts open', () => {
    const finished = [task(1, 'Opening', 'verified', 6), task(2, 'Closing', 'not_started', 22)]
    const { unmount } = render_(finished)
    expect(screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'))).toEqual(['Closing', 'Opening'])
    expect(within(screen.getByRole('region', { name: 'Opening' })).getByText('All done')).toBeTruthy()
    unmount()
    render_(items, { openAll: true })
    expect(screen.getAllByRole('region').every((s) => within(s).getAllByRole('button')[0].getAttribute('aria-expanded') === 'true')).toBe(true)
  })
})
