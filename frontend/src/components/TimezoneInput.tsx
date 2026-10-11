import { useId } from 'react'
import { Input } from '@/components/ui/input'
import { useApi } from '@/lib/useApi'

interface TimezoneInputProps {
  value: string
  onChange: (value: string) => void
}

/** A text box that suggests IANA time zones such as Asia/Kuwait as you type. */
export function TimezoneInput({ value, onChange }: TimezoneInputProps) {
  const listId = useId()
  const zones = useApi<string[]>('/organization/timezones')
  return (
    <>
      <Input required list={listId} value={value} placeholder="Asia/Kuwait" autoComplete="off" onChange={(e) => onChange(e.target.value)} />
      <datalist id={listId}>{zones.data?.map((z) => <option key={z} value={z} />)}</datalist>
    </>
  )
}
