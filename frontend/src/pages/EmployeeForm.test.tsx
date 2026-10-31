import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EmployeeForm, type EmployeeRow } from '@/pages/EmployeeForm'

vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { permissions: ['employee.manage'], role_tier: 'manager', locations: [] } }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async () => true }))
vi.mock('@/lib/useApi', () => ({ useApi: () => ({ data: [{ name: 'steward', label: 'Steward' }] }) }))
vi.mock('@/lib/useLookups', () => ({ useLookup: () => ['Steward', 'Head Chef', 'Butcher'] }))

const titleOptions = () => Array.from((screen.getByLabelText('Job title') as HTMLSelectElement).options).map((o) => o.textContent)

describe('EmployeeForm job title', () => {
  it('offers every job title set up in Settings when adding someone, with none chosen yet', () => {
    render(<EmployeeForm open employee={null} supervisors={[]} onClose={() => {}} onSaved={() => {}} />)
    expect(titleOptions()).toEqual(['Choose a job title', 'Steward', 'Head Chef', 'Butcher'])
    expect((screen.getByLabelText('Job title') as HTMLSelectElement).value).toBe('')
  })

  it('shows the title someone already has when editing, even one that is no longer in the list', () => {
    const person = { id: 1, employee_code: 'E9', full_name: 'Sam', job_title: 'Dishwasher', status: 'active', supervisor_id: null, location_ids: [], role: 'steward' } as EmployeeRow
    render(<EmployeeForm open employee={person} supervisors={[]} onClose={() => {}} onSaved={() => {}} />)
    expect(titleOptions()).toEqual(['Choose a job title', 'Dishwasher', 'Steward', 'Head Chef', 'Butcher'])
    expect((screen.getByLabelText('Job title') as HTMLSelectElement).value).toBe('Dishwasher')
  })
})
