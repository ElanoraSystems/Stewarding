import { describe, expect, it } from 'vitest'
import { cutsUse, type Balance } from '@/lib/units'

const kg: Balance = { qty: 20, unit: 'kg', portioned: 0, left: 20, unmeasured: 0 }

describe('cutsUse', () => {
  it('adds cuts in the same unit', () => {
    expect(cutsUse(kg, [{ qty: '4.8', unit: 'kg' }, { qty: '1.2', unit: 'kg' }])).toBe(6)
  })

  it('converts grams and ignores letter case and spaces', () => {
    expect(cutsUse(kg, [{ qty: '500', unit: ' G ' }, { qty: '1', unit: 'KG' }])).toBe(1.5)
  })

  it('converts litres and millilitres but never mixes mass with volume', () => {
    const litres: Balance = { qty: 10, unit: 'l', portioned: 0, left: 10, unmeasured: 0 }
    expect(cutsUse(litres, [{ qty: '250', unit: 'ml' }, { qty: '2', unit: 'kg' }])).toBe(0.25)
  })

  it('compares an unknown unit only with the same word', () => {
    const trays: Balance = { qty: 10, unit: 'trays', portioned: 0, left: 10, unmeasured: 0 }
    expect(cutsUse(trays, [{ qty: '3', unit: 'Trays' }, { qty: '3', unit: 'kg' }])).toBe(3)
  })

  it('leaves out cuts with no quantity or no unit', () => {
    expect(cutsUse(kg, [{ qty: '', unit: 'kg' }, { qty: '4', unit: '' }])).toBe(0)
  })
})
