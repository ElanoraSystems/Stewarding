import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApproversModal } from '@/pages/ApproversModal'

const mocks = vi.hoisted(() => ({ calls: [] as { path: string; body: unknown }[] }))

vi.mock('@/lib/api', () => ({ api: vi.fn(async (path: string, init: { body: unknown }) => { mocks.calls.push({ path, body: init.body }); return {} }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true } }))
vi.mock('@/lib/useApi', () => ({
  useApi: () => ({ data: [{ id: 5, name: 'Ahmed Ali', job_title: 'Head Chef' }, { id: 9, name: 'Sara Khan', job_title: 'Supervisor' }], reload: () => undefined }),
}))

describe('ApproversModal', () => {
  beforeEach(() => { mocks.calls.length = 0 })

  it('offers the people who can approve and saves the ones ticked, any of whom may decide', async () => {
    const user = userEvent.setup()
    const saved = vi.fn()
    render(<ApproversModal name="Opening checklist" kind="checklists" approvers={[5]} names={['Ahmed Ali']} path="/checklists/templates/3" onClose={() => undefined} onSaved={saved} />)
    expect((screen.getByLabelText(/Ahmed Ali/) as HTMLInputElement).checked).toBe(true)
    await user.click(screen.getByLabelText(/Sara Khan/))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.calls).toEqual([{ path: '/checklists/templates/3', body: { approvers: [5, 9] } }])
    expect(saved).toHaveBeenCalled()
  })

  it('unticking everyone saves an empty list, which means everyone who may approve', async () => {
    const user = userEvent.setup()
    render(<ApproversModal name="Walk-in fridge" kind="monitoring" approvers={[9]} path="/equipment/2" onClose={() => undefined} onSaved={() => undefined} />)
    await user.click(screen.getByLabelText(/Sara Khan/))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.calls[0]).toEqual({ path: '/equipment/2', body: { approvers: [] } })
  })
})
