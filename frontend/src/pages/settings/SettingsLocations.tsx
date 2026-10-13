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
import { currentPosition } from '@/lib/geo'
import { useRun, useToast } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface LocationRow {
  id: number
  code: string
  name: string
  kind: string
  timezone: string
  active: boolean
  latitude: number | null
  longitude: number | null
  geofence_radius_m: number | null
  geofence: boolean
}

const KINDS = ['kitchen', 'restaurant', 'bar', 'banquet', 'station', 'other']
const BLANK = { id: null as number | null, code: '', name: '', kind: 'kitchen', timezone: 'Asia/Kuwait', active: true, latitude: '', longitude: '', radius: '' }

export function SettingsLocations() {
  const run = useRun()
  const toast = useToast()
  const { data, reload } = useApi<{ locations: LocationRow[] }>('/settings')
  const [loc, setLoc] = useState<typeof BLANK | null>(null)
  const org = useApi<{ timezone: string }>('/organization')
  const { refresh } = useAuth()

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!loc) return
    const fence = { latitude: loc.latitude === '' ? null : Number(loc.latitude), longitude: loc.longitude === '' ? null : Number(loc.longitude), geofence_radius_m: loc.radius === '' ? null : Number(loc.radius) }
    const body = loc.id
      ? { name: loc.name, kind: loc.kind, timezone: loc.timezone, active: loc.active, ...fence }
      : { code: loc.code, name: loc.name, kind: loc.kind, timezone: loc.timezone, ...fence }
    const ok = await run(() => api(loc.id ? `/settings/locations/${loc.id}` : '/settings/locations', { method: loc.id ? 'PUT' : 'POST', body }), 'Location saved')
    if (ok) {
      setLoc(null)
      reload()
      await refresh()
    }
  }

  async function useHere() {
    if (!loc) return
    try {
      const here = await currentPosition()
      setLoc({ ...loc, latitude: here.latitude.toFixed(6), longitude: here.longitude.toFixed(6), radius: loc.radius || '100' })
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Could not read your position')
    }
  }

  if (!data) return <Skeleton className="h-48 w-full" />
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">Kitchens, restaurants, bars, banquet areas and stations. Each has its own time zone and an optional area that check-in and check-out are limited to.</p>
        <Button onClick={() => setLoc({ ...BLANK, timezone: org.data?.timezone ?? BLANK.timezone })}>Add location</Button>
      </div>
      <Table>
        <thead><tr><Th>Code</Th><Th>Name</Th><Th>Type</Th><Th>Time zone</Th><Th>Status</Th><Th /></tr></thead>
        <tbody>
          {data.locations.map((l) => (
            <tr key={l.id}>
              <Td>{l.code}</Td><Td className="font-medium">{l.name}</Td><Td>{l.kind}</Td><Td>{l.timezone}</Td>
              <Td><Badge tone={l.active ? 'ok' : 'neutral'}>{l.active ? 'Active' : 'Inactive'}</Badge>{l.geofence && <Badge className="ml-1">Geofence {l.geofence_radius_m} m</Badge>}</Td>
              <Td><Button size="sm" variant="outline" onClick={() => setLoc({ ...BLANK, ...l, latitude: l.latitude === null ? '' : String(l.latitude), longitude: l.longitude === null ? '' : String(l.longitude), radius: l.geofence_radius_m === null ? '' : String(l.geofence_radius_m) })}>Edit</Button></Td>
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
            <fieldset className="space-y-2 rounded-md border border-border p-3">
              <legend className="px-1 text-sm font-medium">Limit check-in and check-out to an area</legend>
              <p className="text-xs text-ink-muted">Staff must be within the radius of this point to check in or out. Leave all three empty for no restriction. Stand at the location and use your current position.</p>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Latitude"><Input type="number" step="any" min={-90} max={90} value={loc.latitude} onChange={(e) => setLoc({ ...loc, latitude: e.target.value })} /></Field>
                <Field label="Longitude"><Input type="number" step="any" min={-180} max={180} value={loc.longitude} onChange={(e) => setLoc({ ...loc, longitude: e.target.value })} /></Field>
                <Field label="Radius (metres)" hint="20 to 5000"><Input type="number" min={20} max={5000} value={loc.radius} onChange={(e) => setLoc({ ...loc, radius: e.target.value })} /></Field>
              </div>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="outline" onClick={useHere}>Use my current position</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setLoc({ ...loc, latitude: '', longitude: '', radius: '' })}>Remove restriction</Button>
              </div>
            </fieldset>
            {loc.id && (
              <>
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
