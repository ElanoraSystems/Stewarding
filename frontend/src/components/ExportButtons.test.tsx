import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ExportButtons } from '@/components/ExportButtons'

const download = vi.fn().mockResolvedValue(true)
vi.mock('@/lib/download', () => ({ downloadFile: (...a: unknown[]) => download(...a) }))
vi.mock('@/lib/toast', () => ({ useToast: () => vi.fn() }))

describe('ExportButtons', () => {
  it('downloads with the filters on screen and the chosen dates', async () => {
    render(<ExportButtons kind="receipts" from="2026-02-01" to="2026-02-28" filters={{ supplier_id: '4', q: 'plate', status: '' }} />)
    fireEvent.click(screen.getByRole('button', { name: /Excel/ }))
    await waitFor(() => expect(download).toHaveBeenCalled())
    const url = String(download.mock.calls[0][0])
    expect(url).toContain('/api/reports/records/receipts/export?')
    for (const part of ['supplier_id=4', 'q=plate', 'date_from=2026-02-01', 'date_to=2026-02-28', 'fmt=xlsx']) expect(url).toContain(part)
    expect(url).not.toContain('status=')
  })

  it('says it exports the last 30 days when no dates are chosen', () => {
    render(<ExportButtons kind="movements" from="" to="" filters={{}} />)
    expect(screen.getByText(/last 30 days/)).toBeTruthy()
  })
})
