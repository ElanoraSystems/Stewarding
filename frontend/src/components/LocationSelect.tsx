import { useEffect } from 'react'
import { Select } from '@/components/ui/select'
import { useAuth } from '@/lib/auth'

interface LocationSelectProps {
  value: number | null
  onChange: (id: number | null) => void
  allowAll?: boolean
  className?: string
}

export function LocationSelect({ value, onChange, allowAll = false, className = 'w-auto min-w-44' }: LocationSelectProps) {
  const { me } = useAuth()
  const locations = me?.locations ?? []

  useEffect(() => {
    if (value === null && !allowAll && locations.length > 0) onChange(locations[0].id)
  }, [value, allowAll, locations, onChange])

  return (
    <Select
      aria-label="Location"
      className={className}
      value={value ?? ''}
      onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
    >
      {allowAll && <option value="">All locations</option>}
      {locations.map((location) => (
        <option key={location.id} value={location.id}>
          {location.name}
        </option>
      ))}
    </Select>
  )
}
