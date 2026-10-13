import { useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { Skeleton, Table, Td, Th } from '@/components/ui/table'
import { TimezoneInput } from '@/components/TimezoneInput'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface LocationRow {
  id: number
  code: string
  name: string
  kind: string
  timezone: string
  active: boolean
  pin_required: boolean
}

const KINDS = ['kitchen', 'restaurant', 'bar', 'banquet', 'station', 'other']
const BLANK = { id: null as number | null, code: '', name: '', kind: 'kitchen', timezone: 'Asia/Kuwait', active: true, pin: '', clear_pin: false }

export function SettingsLocations() {
  const run = useRun()
  const { data, reload } = useApi<{ locations: LocationRow[] }>('/settings')
  const [loc, setLoc] = useState<typeof BLANK | null>(null)
  const org = useApi<{ timezone: string }>('/organization')
  const { refresh } = useAuth()

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!loc) return
    const body = loc.id
      ? { name: loc.name, kind: loc.kind, timezone: loc.timezone, active: loc.active, pin: loc.pin || undefined, clear_pin: loc.clear_pin }
      : { code: loc.code, name: loc.name, kind: loc.kind, timezone: loc.timezone, pin: loc.pin || undefined }
    const ok = await run(() => api(loc.id ? `/settings/locations/${loc.id}` : '/settings/locations', { method: loc.id ? 'PUT' : 'POST', body }), 'Location saved')
    if (ok) {
      setLoc(null)
      reload()
      await refresh()
    }
  }

  if (!data) return <Skeleton className="h-48 w-full" />
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">Kitchens, restaurants, bars, banquet areas and stations. Each has its own time zone and optional check-in PIN.</p>
        <Button onClick={() => setLoc({ ...BLANK, timezone: org.data?.timezone ?? BLANK.timezone })}>Add location</Button>
      </div>
      <Table>
        <thead><tr><Th>Code</Th><Th>Name</Th><Th>Type</Th><Th>Time zone</Th><Th>Status</Th><Th /></tr></thead>
        <tbody>
          {data.locations.map((l) => (
            <tr key={l.id}>
              <Td>{l.code}</Td><Td className="font-medium">{l.name}</Td><Td>{l.kind}</Td><Td>{l.timezone}</Td>
              <Td><Badge tone={l.active ? 'ok' : 'neutral'}>{l.active ? 'Active' : 'Inactive'}</Badge>{l.pin_required && <Badge className="ml-1">PIN</Badge>}</Td>
              <Td><Button size="sm" variant="outline" onClick={() => setLoc({ ...BLANK, ...l, pin: '' })}>Edit</Button></Td>
            </tr>
          ))}
        </tbody>
      </Table>

      <Modal open={loc !== null} title={loc?.id ? 'Edit location' : 'Add location'} onClose={() => setLoc(null)}>
        {loc && (
          <form onSubmit={save} className="space-y-3">
            {!loc.id && <Field label="Code"><Input required value={loc.code} onChange={(e) => setLoc({ ...loc, code: e.target.value })} /></Field>}
            <Field label="Name"><Input required value={loc.name} onChange={(e) => setLoc({ ...loc, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type"><Select value={loc.kind} onChange={(e) => setLoc({ ...loc, kind: e.target.value })}>{KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</Select></Field>
              <Field label="Time zone" hint="Shift times, check-ins and report dates at this location use it."><TimezoneInput value={loc.timezone} onChange={(zone) => setLoc({ ...loc, timezone: zone })} /></Field>
            </div>
            <Field label="Check-in PIN (4-8 digits)" hint="Leave blank to keep the current PIN."><Input inputMode="numeric" autoComplete="off" value={loc.pin} onChange={(e) => setLoc({ ...loc, pin: e.target.value })} /></Field>
            {loc.id && (
              <>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={loc.clear_pin} onChange={(e) => setLoc({ ...loc, clear_pin: e.target.checked })} /> Remove the PIN requirement</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={loc.active} onChange={(e) => setLoc({ ...loc, active: e.target.checked })} /> Location is active</label>
              </>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setLoc(null)}>Cancel</Button>
              <Button type="submit">Save</Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
