let displayZone: string | undefined

/** Zone used when a time has no location of its own; set from the organization settings. */
export function setDisplayTimeZone(zone: string | undefined) {
  displayZone = zone
}

export function fmtDateTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return '-'
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: timeZone ?? displayZone }).format(new Date(iso))
}

export function fmtTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return '-'
  return new Intl.DateTimeFormat('en-GB', { timeStyle: 'short', timeZone: timeZone ?? displayZone }).format(new Date(iso))
}

/** Formats a plain YYYY-MM-DD date without applying any timezone shift. */
export function fmtDate(day: string | null | undefined): string {
  if (!day) return '-'
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${day}T00:00:00Z`))
}

export function hoursMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '-'
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export function label(value: string): string {
  const spaced = value.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function weekRange(day: string): { from: string; to: string } {
  const date = new Date(`${day}T00:00:00Z`)
  const offset = (date.getUTCDay() + 6) % 7
  const monday = new Date(date.getTime() - offset * 86400000)
  const sunday = new Date(monday.getTime() + 6 * 86400000)
  return { from: monday.toISOString().slice(0, 10), to: sunday.toISOString().slice(0, 10) }
}
