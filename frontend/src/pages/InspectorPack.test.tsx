import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { InspectorPack } from '@/pages/InspectorPack'

const mocks = vi.hoisted(() => ({ download: vi.fn(async (_path: string, _name: string) => true), toast: vi.fn() }))
vi.mock('@/lib/download', () => ({ downloadFile: mocks.download }))
vi.mock('@/lib/toast', () => ({ useToast: () => mocks.toast }))
vi.mock('@/components/LocationSelect', () => ({ LocationSelect: () => <select aria-label="Location pick" /> }))

describe('InspectorPack', () => {
  beforeEach(() => { mocks.download.mockClear(); mocks.toast.mockClear() })

  it('downloads the pack for the chosen dates', async () => {
    render(<InspectorPack canExport />)
    await userEvent.click(screen.getByRole('button', { name: /Download PDF/ }))
    const path = mocks.download.mock.calls[0][0]
    expect(path).toMatch(/^\/api\/reports\/inspector-pack\?date_from=\d{4}-\d{2}-\d{2}&date_to=\d{4}-\d{2}-\d{2}/)
  })

  it('says so when the pack cannot be made, and hides the button without export permission', async () => {
    mocks.download.mockResolvedValueOnce(false)
    const { unmount } = render(<InspectorPack canExport />)
    await userEvent.click(screen.getByRole('button', { name: /Download PDF/ }))
    expect(mocks.toast).toHaveBeenCalledWith('error', expect.stringContaining('Could not create the inspector pack'))
    unmount()
    render(<InspectorPack canExport={false} />)
    expect(screen.queryByRole('button', { name: /Download PDF/ })).toBeNull()
  })
})
