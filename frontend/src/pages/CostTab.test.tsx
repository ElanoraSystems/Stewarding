import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CostTab } from '@/pages/CostTab'

const totals = { opening_value: 2241, purchases: 20, returns: -4.952, transfers_in: 0, transfers_out: 0, closing_value: 2256.048, cost_consumed: 5.412, issued: 0, breakage_damage: 0, count_adjustments: -5.412 }
vi.mock('@/components/LocationSelect', () => ({ LocationSelect: () => null }))
vi.mock('@/lib/useApi', () => ({
  qs: () => '',
  useApi: () => ({ loading: false, error: null, data: { totals, by_category: [] } }),
}))

describe('CostTab', () => {
  it('shows how the cost consumed is made up, naming a count shortage as the cause', () => {
    render(<CostTab />)
    expect(screen.getByText(/How Cost consumed is worked out/)).toBeTruthy()
    expect(screen.getByText(/Count shortages 5\.412/)).toBeTruthy()
  })
})
