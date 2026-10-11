export const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export type Range = [string, string]

const shift = (d: Date, days: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + days)

function weekStart(d: Date): Date {
  return shift(d, -((d.getDay() + 6) % 7))
}

export const PRESETS: { key: string; label: string; range: () => Range }[] = [
  { key: 'today', label: 'Today', range: () => [iso(new Date()), iso(new Date())] },
  { key: 'yesterday', label: 'Yesterday', range: () => { const y = iso(shift(new Date(), -1)); return [y, y] } },
  { key: 'week', label: 'This week', range: () => { const s = weekStart(new Date()); return [iso(s), iso(shift(s, 6))] } },
  { key: 'lastweek', label: 'Last week', range: () => { const s = shift(weekStart(new Date()), -7); return [iso(s), iso(shift(s, 6))] } },
  { key: 'month', label: 'This month', range: () => { const n = new Date(); return [iso(new Date(n.getFullYear(), n.getMonth(), 1)), iso(new Date(n.getFullYear(), n.getMonth() + 1, 0))] } },
  { key: 'lastmonth', label: 'Last month', range: () => { const n = new Date(); return [iso(new Date(n.getFullYear(), n.getMonth() - 1, 1)), iso(new Date(n.getFullYear(), n.getMonth(), 0))] } },
]
