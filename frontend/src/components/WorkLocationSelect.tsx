import { useEffect, useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { Skeleton } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { useApi } from '@/lib/useApi'

interface Props {
  value: number | null
  onChange: (id: number | null) => void
}

/** The location picker for people who work shifts: fixed to the one location they are rostered at today, with a link to pick another. */
export function WorkLocationSelect({ value, onChange }: Props) {
  const { me } = useAuth()
  const status = useApi<{ rostered_today: { location_id: number; location_name: string; week_off: boolean }[] }>(
    me?.permissions.includes('attendance.self') ? '/attendance/me/status' : null)
  const [elsewhere, setElsewhere] = useState(false)
  const working = (status.data?.rostered_today ?? []).filter((r) => !r.week_off)
  const only = new Set(working.map((r) => r.location_id)).size === 1 ? working[0] : null
  const locked = only !== null && !elsewhere && (value === null || value === only.location_id)

  useEffect(() => {
    if (locked && value === null) onChange(only.location_id)
  }, [locked, value, only, onChange])

  if (status.loading) return <Skeleton className="h-10 w-44" />
  if (!locked) return <LocationSelect value={value} onChange={onChange} />
  return (
    <div className="flex flex-wrap items-center gap-x-3">
      <span className="flex h-10 items-center rounded-lg border border-border bg-surface-muted px-3 text-sm font-medium">{only.location_name} (rostered today)</span>
      <button type="button" className="min-h-11 text-sm font-medium text-brand-deep hover:underline" onClick={() => setElsewhere(true)}>Viewing another location?</button>
    </div>
  )
}
