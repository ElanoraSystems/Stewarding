import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsHaccp } from '@/pages/settings/SettingsHaccp'

const mocks = vi.hoisted(() => ({ calls: [] as { path: string; init: { method?: string; body?: Record<string, unknown> } }[], downloads: [] as string[], perms: ['equipment.manage'] }))
const hz = (over = {}) => ({ hazard: 'Pathogens survive', kind: 'Biological', significant: true, control: 'Core temperature checked', basis: '', ...over })
const step = (name: string, over = {}) => ({ name, kind: 'step', control: '', no_action: '', hazards: [hz()], no_hazard: '', ...over })
const plan = {
  owner: 'Head Chef', team: '', scope: '', products: '', review: 'Yearly', version: 2, saved: true, revisions: [{ version: 2, date: '27 Nov 2026', by: 'Ashfaque', note: 'Added fish' }],
  processes: [
    { name: 'Hot food', references: 'CXC 1-1969', confirmed_on: '', confirmed_by: '', steps: [step('Receiving'), step('Within limits?', { kind: 'decision', no_action: 'Reject and return' }), step('Cooling', { control: 'CCP' })] },
    { name: 'Bakery', references: '', confirmed_on: '', confirmed_by: '', steps: [step('Baking')] },
  ],
}
const versions = [{ version: 2, current: true, saved_at: '2026-11-27T10:00:00Z', by: 'Ashfaque', note: 'Added fish' }, { version: 1, current: false, saved_at: '2026-11-01T10:00:00Z', by: 'Ashfaque', note: 'First version' }]

vi.mock('@/lib/api', () => ({ api: vi.fn(async (path: string, init: { method?: string; body?: Record<string, unknown> }) => { mocks.calls.push({ path, init }); return {} }) }))
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ me: { permissions: mocks.perms } }) }))
vi.mock('@/lib/download', () => ({ downloadFile: vi.fn(async (path: string) => { mocks.downloads.push(path); return true }) }))
vi.mock('@/lib/toast', () => ({ useRun: () => async (action: () => Promise<unknown>) => { await action(); return true }, useToast: () => vi.fn() }))
vi.mock('@/lib/useApi', async (original) => ({ ...(await original<typeof import('@/lib/useApi')>()), useApi: (path: string) => ({ data: path === '/haccp/plan/versions' ? versions : plan, loading: false, error: null, reload: vi.fn() }) }))
vi.mock('@/components/LocationSelect', () => ({ LocationSelect: () => <select aria-label="Location" /> }))

describe('SettingsHaccp', () => {
  beforeEach(() => { mocks.calls.length = 0; mocks.downloads.length = 0; mocks.perms = ['equipment.manage'] })

  it('saves the edited text, and a new version only when it is named', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    expect(screen.getByText(/version 2/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('HACCP team'), { target: { value: 'Chef and supervisor' } })
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(mocks.calls[0].path).toBe('/haccp/plan')
    expect(mocks.calls[0].init.body).toMatchObject({ team: 'Chef and supervisor', new_version: false, processes: [{ name: 'Hot food', references: 'CXC 1-1969' }, { name: 'Bakery' }] })
    const newVersion = screen.getByRole('button', { name: 'Save as version 3' }) as HTMLButtonElement
    expect(newVersion.disabled).toBe(true)
    await user.type(screen.getByLabelText(/what changed/), 'Added reheating')
    await user.click(newVersion)
    expect(mocks.calls[1].init.body).toMatchObject({ new_version: true, note: 'Added reheating' })
  })

  it('lets someone without permission to set monitoring up read it but not change it', () => {
    mocks.perms = []
    render(<SettingsHaccp />)
    expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull()
    expect((screen.getByLabelText('HACCP team') as HTMLTextAreaElement).disabled).toBe(true)
    expect(screen.queryByRole('button', { name: 'Restore version 1' })).toBeNull()
  })

  it('will not save a step that has no hazard until it has one or says why it has none, so the flow and the analysis cannot disagree', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    const save = screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement
    expect(save.disabled).toBe(false)
    await user.click(screen.getAllByRole('button', { name: 'Add a step' })[1])  // Bakery
    expect(screen.getByText('Give the step a name.')).toBeTruthy()
    await user.type(screen.getByLabelText('Bakery step 2'), 'Cooling on racks')
    expect(screen.getByText('Add a hazard, or say why this step has none.')).toBeTruthy()
    expect(save.disabled).toBe(true)
    await user.type(screen.getByLabelText('Bakery step 2 why no hazard'), 'Covered by the next step')
    expect(save.disabled).toBe(false)
    await user.click(save)
    const sent = mocks.calls[0].init.body as { processes: { steps: { name: string; no_hazard: string; hazards: unknown[] }[] }[] }
    expect(sent.processes[1].steps[1]).toMatchObject({ name: 'Cooling on racks', no_hazard: 'Covered by the next step', hazards: [] })
  })

  it('asks a decision what happens on no, and a control step for a significant hazard', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    const save = screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement
    await user.click(screen.getAllByRole('button', { name: 'Add a yes/no decision' })[0])
    await user.type(screen.getByLabelText('Hot food step 4'), 'Held at or above the limit?')
    await user.type(screen.getByLabelText('Hot food step 4 why no hazard'), 'Checked at the next step')
    expect(screen.getByText('Say what happens when the answer is no.')).toBeTruthy()
    expect(save.disabled).toBe(true)
    await user.type(screen.getByLabelText('Hot food step 4 if no'), 'Reheat once or discard')
    expect(save.disabled).toBe(false)
    await user.selectOptions(screen.getByLabelText('Control level of Hot food step 4'), 'CCP')
    expect(screen.getByText('A CCP step needs a significant hazard that it controls.')).toBeTruthy()
    expect(save.disabled).toBe(true)
  })

  it('lets hazards be added to a step and sent with it, in the order of the flow', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    await user.click(screen.getAllByRole('button', { name: 'Add a hazard to step 1' })[0])
    await user.type(screen.getByLabelText('Hot food step 1 hazard 2'), 'Foreign bodies in the delivery')
    await user.type(screen.getByLabelText('Hot food step 1 control measure 2'), 'Inspect the load')
    await user.click(screen.getByRole('button', { name: 'Move Hot food step 3 up' }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    const sent = mocks.calls[0].init.body as { processes: { steps: { name: string; hazards: { hazard: string }[] }[] }[] }
    expect(sent.processes[0].steps.map((s) => s.name)).toEqual(['Receiving', 'Cooling', 'Within limits?'])
    expect(sent.processes[0].steps[0].hazards.map((h) => h.hazard)).toEqual(['Pathogens survive', 'Foreign bodies in the delivery'])
  })

  it('lists every version, prints an earlier one, and restores it only after a confirmation', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    expect(screen.getByText('Version 1')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Download version 1 as PDF' }))
    expect(mocks.downloads[0]).toContain('version=1')
    await user.click(screen.getByRole('button', { name: 'Restore version 1' }))
    expect(mocks.calls).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, restore' }))
    expect(mocks.calls[0]).toMatchObject({ path: '/haccp/plan/versions/1/restore', init: { method: 'POST' } })
  })
})
