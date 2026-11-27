import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ManagerDashboard } from '@/pages/ManagerDashboard'

const dash = {
  kpis: { scheduled_today: 4, checked_in: 2, not_checked_in: 2, absent: 0, on_duty: 2, daily_completion: { numerator: 5, denominator: 5, percent: 100 }, weekly_completion: { numerator: 5, denominator: 5, percent: 100 },
    overdue_tasks: 0, awaiting_approval: { tasks: 0, readings: 0, breakage: 0 }, monitoring_checks: { done: 21, due: 33 }, failed_checks: 0, equipment_attention: 0, inventory: { qty: 0, value: 0 },
    off_today: 0, low_stock_items: 0, breakage_today: 0, breakage_month: 0 },
  charts: { task_trend: [], weekly_compliance: [], breakage_trend: [], inventory_movement: [], attendance_trend: [],
    monitoring_compliance: [
      { equipment: 'Chiller 1', location: 'Beach', due: 28, done: 27, failed: 0, percent: 96.4 },
      { equipment: 'Chiller 2', location: 'Beach', due: 28, done: 27, failed: 0, percent: 96.4 },
      { equipment: 'Sanitiser', location: 'Basement', due: 14, done: 10, failed: 0, percent: 71.4 },
    ] },
}

vi.mock('@/lib/useApi', async (original) => ({ ...(await original<typeof import('@/lib/useApi')>()), useApi: (path: string | null) => ({ data: path?.startsWith('/dashboard') ? dash : null, loading: false, error: null, reload: vi.fn() }) }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { permissions: [], employee: { name: 'Ashfaque Ahmed' }, locations: [] } }) }))
vi.mock('@/pages/CompliancePanel', () => ({ CompliancePanel: () => null }))
vi.mock('@/components/LocationSelect', () => ({ LocationSelect: () => <select aria-label="Location" /> }))

const open = () => render(<MemoryRouter><ManagerDashboard /></MemoryRouter>)

describe('ManagerDashboard tidy layout', () => {
  it('keeps the date and status filters behind a button until they are wanted', () => {
    open()
    expect(screen.queryByLabelText('From date')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'More filters' }))
    expect(screen.getByLabelText('From date')).toBeTruthy()
  })

  it('says which period each number is for', () => {
    open()
    expect(screen.getByText("Today's completion")).toBeTruthy()
    expect(screen.getByText("This week's completion")).toBeTruthy()
    expect(screen.getByText('Checks recorded today')).toBeTruthy()
  })

  it('shows only the points below 95% or with a failure until asked for all of them', () => {
    open()
    expect(screen.getByText(/Sanitiser \(Basement\)/)).toBeTruthy()
    expect(screen.queryByText(/Chiller 1/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Show all 3 points \(2 are at 95% or better\)/ }))
    expect(screen.getByText(/Chiller 1/)).toBeTruthy()
  })
})
