import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ColumnChart } from '@/components/charts'

const days = Array.from({ length: 30 }, (_, i) => ({ date: `2026-10-${String(i + 1).padStart(2, '0')}`, in: i % 3 === 0 ? 40 : 0, out: 10 }))

describe('ColumnChart', () => {
  it('shows readable dates, a value scale and the totals, and says so when there is nothing', () => {
    const { rerender } = render(<ColumnChart data={days} labelKey="date" series={[{ key: 'in', label: 'In', className: 'bg-ok' }, { key: 'out', label: 'Out', className: 'bg-warn' }]} />)
    expect(screen.getAllByText('1 Oct').length).toBeGreaterThan(0)  // not cut to "10..."
    expect(screen.getByText('50')).toBeTruthy()  // the top of the scale is a round number
    expect(screen.getByText(/In:/).textContent).toContain('400')
    rerender(<ColumnChart data={days.map((d) => ({ ...d, in: 0, out: 0 }))} labelKey="date" series={[{ key: 'in', label: 'In', className: 'bg-ok' }]} empty="No breakage in this period." />)
    expect(screen.getByText('No breakage in this period.')).toBeTruthy()
  })
})
