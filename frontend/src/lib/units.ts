export interface Balance {
  qty: number
  unit: string
  portioned: number
  left: number
  unmeasured: number
}

// What a unit measures and its size in the smallest unit; any other unit only compares with itself.
const UNITS: Record<string, [string, number]> = { kg: ['mass', 1000], g: ['mass', 1], l: ['volume', 1000], ml: ['volume', 1] }

const measure = (unit: string): [string, number] => {
  const name = unit.trim().toLowerCase()
  return UNITS[name] ?? [name, 1]
}

/** What the cuts typed so far use, in the lot's own unit; cuts with no quantity or in an unrelated unit are left out. */
export function cutsUse(balance: Balance, cuts: { qty: string; unit: string }[]): number {
  const [kind, size] = measure(balance.unit)
  const total = cuts.reduce((sum, cut) => {
    if (cut.qty === '' || !cut.unit.trim()) return sum
    const [cutKind, cutSize] = measure(cut.unit)
    return cutKind === kind ? sum + Number(cut.qty) * cutSize : sum
  }, 0)
  return Math.round((total / size) * 100) / 100
}
