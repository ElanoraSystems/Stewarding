import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsHaccp } from '@/pages/settings/SettingsHaccp'

const mocks = vi.hoisted(() => ({ calls: [] as { path: string; init: { method?: string; body?: Record<string, unknown> } }[], downloads: [] as string[], perms: ['equipment.manage'] }))
const plan = {
  owner: 'Head Chef', team: '', scope: '', products: '', review: 'Yearly', version: 2, saved: true, revisions: [{ version: 2, date: '27 Nov 2026', by: 'Ashfaque', note: 'Added fish' }],
  processes: [{ name: 'Hot food', steps: [{ name: 'Receiving', control: '' }, { name: 'Cooking', control: '' }, { name: 'Cooling', control: 'CCP' }] }, { name: 'Salads', steps: [{ name: 'Washing', control: '' }] }],
  hazards: [{ step: 'Cooking', hazard: 'Pathogens survive', kind: 'Biological', significant: true, control: 'Core temperature checked', process: '' }],
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

  it('saves the edited text and hazards, and a new version only when it is named', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    expect(screen.getByText(/version 2/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('HACCP team'), { target: { value: 'Chef and supervisor' } })
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(mocks.calls[0].path).toBe('/haccp/plan')
    expect(mocks.calls[0].init.body).toMatchObject({ team: 'Chef and supervisor', new_version: false, hazards: [{ step: 'Cooking' }] })
    const newVersion = screen.getByRole('button', { name: 'Save as version 3' }) as HTMLButtonElement
    expect(newVersion.disabled).toBe(true)  // nothing said about what changed
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
    expect(screen.getByRole('button', { name: /Download PDF/ })).toBeTruthy()
  })

  it('has a flow for each kind of food that can be reordered, tagged, added and sent in that order', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    expect(screen.getByLabelText('Flow preview of Hot food').textContent).toContain('3. CoolingCCP')
    expect(screen.getByLabelText('Flow preview of Salads').textContent).toContain('1. Washing')
    await user.click(screen.getByRole('button', { name: 'Move Hot food step 3 up' }))
    await user.selectOptions(screen.getByLabelText('Control level of Hot food step 2'), 'OPRP')
    await user.click(screen.getByRole('button', { name: /Add a kind of food/ }))
    await user.type(screen.getByLabelText('Process 3 name'), 'Sushi')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    const sent = mocks.calls[0].init.body as { processes: { name: string; steps: { name: string; control: string }[] }[] }
    expect(sent.processes.map((p) => p.name)).toEqual(['Hot food', 'Salads', 'Sushi'])
    expect(sent.processes[0].steps).toEqual([{ name: 'Receiving', control: '' }, { name: 'Cooling', control: 'OPRP' }, { name: 'Cooking', control: '' }])
  })

  it('says which kind of food a hazard applies to', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    await user.selectOptions(screen.getByLabelText('Applies to 1'), 'Salads')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(mocks.calls[0].init.body).toMatchObject({ hazards: [{ process: 'Salads' }] })
  })

  it('lists every version, prints an earlier one, and restores it only after a confirmation', async () => {
    const user = userEvent.setup()
    render(<SettingsHaccp />)
    expect(screen.getByText('Version 1')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Download version 1 as PDF' }))
    expect(mocks.downloads[0]).toContain('version=1')
    await user.click(screen.getByRole('button', { name: 'Restore version 1' }))
    expect(mocks.calls).toHaveLength(0)  // asks first
    await user.click(screen.getByRole('button', { name: 'Yes, restore' }))
    expect(mocks.calls[0]).toMatchObject({ path: '/haccp/plan/versions/1/restore', init: { method: 'POST' } })
  })
})
