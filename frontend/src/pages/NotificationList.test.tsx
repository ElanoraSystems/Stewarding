import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { groupNotes, type Note } from '@/lib/notes'
import { NotificationList } from '@/pages/NotificationList'

const note = (id: number, over: Partial<Note> = {}): Note => ({ id, kind: 'task_escalated', title: `Escalation: ${id} tasks open`, body: null, priority: 'critical', location_id: 2, link: '/checklists', created_at: '2026-11-26T10:00:00Z', read_at: null, requires_ack: true, acknowledged_at: null, action_needed: true, ...over })
const props = (items: Note[]) => ({ items, places: new Map([[2, 'Beach Kitchen']]), canDecide: true, selected: [], onToggle: vi.fn(), onRead: vi.fn(), onAcknowledge: vi.fn(), onDecide: vi.fn() })

describe('NotificationList', () => {
  it('groups neighbouring alerts of one kind, place and day', () => {
    const groups = groupNotes([note(1), note(2), note(3, { location_id: 3 }), note(4, { created_at: '2026-11-20T10:00:00Z' })])
    expect(groups.map((g) => g.length)).toEqual([2, 1, 1])
  })

  it('titles a group by what the alerts have in common, never by one person, and leaves unknown kinds alone', () => {
    const who = (id: number, name: string) => note(id, { kind: 'missed_checkout', title: `${name} has not checked out`, requires_ack: false, action_needed: false })
    render(<MemoryRouter><NotificationList {...props([who(1, 'Jafrudin Shekh'), who(2, 'Simon Wanderi')])} /></MemoryRouter>)
    expect(screen.getByText('Not checked out')).toBeTruthy()
    expect(screen.queryByText('Jafrudin Shekh has not checked out')).toBeNull()  // names appear only when the group is opened
    expect(groupNotes([note(3, { kind: 'something_new' }), note(4, { kind: 'something_new' })]).map((g) => g.length)).toEqual([1, 1])
  })

  it('warns with one Acknowledge button, never Approve and Reject, and acknowledges a whole group', async () => {
    const user = userEvent.setup()
    const p = props([note(1), note(2), note(3)])
    render(<MemoryRouter><NotificationList {...p} /></MemoryRouter>)
    expect(screen.getByText('Escalation to manager')).toBeTruthy()
    expect(screen.getByText(/3 alerts/)).toBeTruthy()
    expect(screen.queryByText('Escalation: 1 tasks open')).toBeNull()  // folded until opened
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Acknowledge all (3)' }))
    expect(p.onAcknowledge).toHaveBeenCalledWith([1, 2, 3])
    await user.click(screen.getByRole('button', { name: /Escalation to manager/ }))
    expect(screen.getByText('Escalation: 1 tasks open')).toBeTruthy()
  })

  it('keeps Approve and Reject for a real request and hides Acknowledge from people who do not decide', () => {
    const request = note(9, { kind: 'breakage_approval', title: 'Approval needed: BRK-1' })
    const { unmount } = render(<MemoryRouter><NotificationList {...props([request])} /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Approve' })).toBeTruthy()
    unmount()
    render(<MemoryRouter><NotificationList {...props([note(1)])} canDecide={false} /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).toBeNull()
  })
})
