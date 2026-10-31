import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { JobTitlesModal } from '@/pages/JobTitlesModal'

const mocks = vi.hoisted(() => ({ api: vi.fn(async () => ({})) }))
vi.mock('@/lib/api', () => ({ api: mocks.api }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => (await action(), true) }))
vi.mock('@/lib/useLookups', () => ({ useLookup: () => ['Steward', 'Head Chef', 'Butcher'] }))

describe('JobTitlesModal', () => {
  it('offers the job titles from Settings and saves the ticked ones to the path it is given', async () => {
    mocks.api.mockClear()
    const user = userEvent.setup()
    render(<JobTitlesModal point={{ id: 7, name: 'Opening checklist', visible_to: null }} path="/checklists/templates/7" title="Who sees Opening checklist" onClose={() => {}} onSaved={() => {}} />)
    expect(screen.getByLabelText('Butcher')).toBeTruthy()
    await user.click(screen.getByLabelText('Head Chef'))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.api).toHaveBeenCalledWith('/checklists/templates/7', { method: 'PUT', body: { visible_to: ['Head Chef'] } })
  })

  it('keeps saving to the monitoring point by default, and still shows a chosen title that was later retired', async () => {
    mocks.api.mockClear()
    const user = userEvent.setup()
    render(<JobTitlesModal point={{ id: 3, name: 'Freezer', visible_to: ['Old Title'] }} onClose={() => {}} onSaved={() => {}} />)
    expect((screen.getByLabelText('Old Title') as HTMLInputElement).checked).toBe(true)
    await user.click(screen.getByLabelText('Old Title'))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.api).toHaveBeenCalledWith('/equipment/3', { method: 'PUT', body: { visible_to: [] } })
  })
})
