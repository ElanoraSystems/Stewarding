import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MyWorkList, type MyWork, type WorkItem } from '@/pages/MyWorkList'

const item = (over: Partial<WorkItem>): WorkItem => ({ kind: 'task', key: 'k', title: 'Task', location_id: 1, location: 'Main Kitchen', due_at: '2026-03-02T10:00:00Z', state: 'due_soon', late_minutes: null, ...over })

function Landing() {
  const loc = useLocation()
  return <p>arrived {loc.pathname} {JSON.stringify(loc.state)}</p>
}

function show(work: MyWork) {
  return render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<MyWorkList work={work} timezoneOf={() => 'UTC'} showPlace={false} />} />
        <Route path="*" element={<Landing />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('MyWorkList', () => {
  it('puts overdue first, then the earliest due, with a chip and the late tag on each row', () => {
    show({ next: null, items: [
      item({ key: 'a', title: 'Later task', due_at: '2026-03-02T15:00:00Z' }),
      item({ key: 'b', title: 'Soon check', kind: 'check', equipment_id: 5, due_at: '2026-03-02T11:00:00Z', state: 'due_now' }),
      item({ key: 'c', title: 'Late task', due_at: '2026-03-02T08:00:00Z', state: 'overdue', late_minutes: 75 }),
      item({ key: 'd', title: 'Later overdue check', kind: 'check', due_at: '2026-03-02T09:00:00Z', state: 'overdue' }),
    ] })
    const rows = screen.getAllByRole('listitem')
    expect(rows.map((r) => within(r).getByText(/task|check/i, { selector: 'p.font-semibold' }).textContent)).toEqual(['Late task', 'Later overdue check', 'Soon check', 'Later task'])
    expect(within(rows[0]).getByText('Overdue')).toBeTruthy()
    expect(within(rows[0]).getByText('Late by 1 h 15 min')).toBeTruthy()
    expect(within(rows[2]).getByText('Due now')).toBeTruthy()
    expect(within(rows[3]).getByText('Due soon')).toBeTruthy()
    expect(within(rows[0]).getByText(/Due .*08:00/)).toBeTruthy()
  })

  it('has one button per row that goes to the right screen with the item preselected', async () => {
    const user = userEvent.setup()
    show({ next: null, items: [
      item({ key: 'a', title: 'Check chiller', kind: 'check', equipment_id: 7, location_id: 3, state: 'overdue' }),
      item({ key: 'b', title: 'Clean drains', due_at: '2026-03-02T12:00:00Z' }),
      item({ key: 'c', title: 'Check probe P1', kind: 'calibration', due_at: null, note: 'Never checked', state: 'overdue' }),
    ] })
    expect(screen.getAllByRole('link')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Do it: Clean drains' }).getAttribute('href')).toBe('/checklists')
    expect(screen.getByText('Never checked')).toBeTruthy()
    await user.click(screen.getByRole('link', { name: 'Record: Check chiller' }))
    expect(screen.getByText('arrived /monitoring {"locationId":3,"equipmentId":7}')).toBeTruthy()
  })

  it('sends a probe check to the calibration page', () => {
    show({ next: null, items: [item({ kind: 'calibration', title: 'Check probe P1' })] })
    expect(screen.getByRole('link', { name: 'Check probe: Check probe P1' }).getAttribute('href')).toBe('/calibration')
  })

  it('says nothing is due and what comes next', () => {
    show({ items: [], next: { title: 'Chiller 1 (air temp)', due_at: '2026-03-02T14:30:00Z', location_id: 1 } })
    expect(screen.getByText('Nothing due right now')).toBeTruthy()
    expect(screen.getByText('Next: Chiller 1 (air temp) at 14:30')).toBeTruthy()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('shows the eight most urgent and the rest on request', async () => {
    const user = userEvent.setup()
    show({ next: null, items: Array.from({ length: 12 }, (_, i) => item({ key: `t${i}`, title: `Task ${i}`, due_at: `2026-03-02T${String(10 + i).padStart(2, '0')}:00:00Z` })) })
    expect(screen.getAllByRole('listitem')).toHaveLength(8)
    await user.click(screen.getByRole('button', { name: 'Show all 12' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(12)
  })

  it('names the place only when the person works at more than one', () => {
    const { unmount } = show({ next: null, items: [item({})] })
    expect(screen.queryByText(/Main Kitchen/)).toBeNull()
    unmount()
    render(<MemoryRouter><MyWorkList work={{ next: null, items: [item({})] }} timezoneOf={() => 'UTC'} showPlace /></MemoryRouter>)
    expect(screen.getByText(/Main Kitchen/)).toBeTruthy()
  })
})
