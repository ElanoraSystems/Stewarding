import { MapPin, Trash2, Upload } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { TimezoneInput } from '@/components/TimezoneInput'
import { SignedNumberInput } from '@/components/ui/signed-number-input'
import { currentPosition } from '@/lib/geo'
import { api, uploadLogo } from '@/lib/api'
import { useRun, useToast } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Organization {
  name: string
  legal_name: string
  address: string
  phone: string
  email: string
  website: string
  registration_number: string
  report_footer: string
  timezone: string
  currency: string
  latitude: number | null
  longitude: number | null
  geofence_radius_m: number | null
  logo: string | null
}

/** The work area is edited as text in three fields, saved with the rest of the organization. */
interface Area {
  latitude: string
  longitude: string
  radius: string
}

type TextKey = Exclude<keyof Organization, 'logo' | 'latitude' | 'longitude' | 'geofence_radius_m'>

const FIELDS: [TextKey, string][] = [
  ['name', 'Organization name'],
  ['legal_name', 'Legal name'],
  ['address', 'Address'],
  ['phone', 'Phone'],
  ['email', 'Email'],
  ['website', 'Website'],
  ['registration_number', 'Registration or licence number'],
  ['report_footer', 'Report footer note'],
  ['timezone', 'Time zone'],
  ['currency', 'Currency (for example KWD)'],
]

export function SettingsOrganization() {
  const run = useRun()
  const toast = useToast()
  const { data, reload } = useApi<Organization>('/organization')
  const [draft, setDraft] = useState<Partial<Organization>>({})
  const [area, setArea] = useState<Partial<Area>>({})
  const [version, setVersion] = useState(0)

  if (!data) return null
  const value = (key: TextKey) => draft[key] ?? data[key]
  const areaValue = (key: keyof Area) => area[key] ?? (key === 'radius' ? data.geofence_radius_m : data[key])?.toString() ?? ''
  const mapsLink = areaValue('latitude') && areaValue('longitude') ? `https://www.google.com/maps?q=${areaValue('latitude')},${areaValue('longitude')}` : null

  async function useHere() {
    try {
      const here = await currentPosition()
      setArea((a) => ({ ...a, latitude: here.latitude.toFixed(6), longitude: here.longitude.toFixed(6), radius: areaValue('radius') || '100' }))
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Could not read your position')
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    const number = (v: string) => (v.trim() === '' ? null : Number(v))
    const body = {
      ...Object.fromEntries(FIELDS.map(([key]) => [key, value(key) || null])),
      latitude: number(areaValue('latitude')), longitude: number(areaValue('longitude')), geofence_radius_m: number(areaValue('radius')),
    }
    if (await run(() => api('/organization', { method: 'PUT', body }), 'Organization saved')) {
      setDraft({})
      setArea({})
      reload()
      window.dispatchEvent(new Event('organization-changed'))
    }
  }

  async function chooseLogo(file: File | undefined) {
    if (file && await run(() => uploadLogo(file), 'Logo updated')) {
      setVersion((v) => v + 1)
      reload()
      window.dispatchEvent(new Event('organization-changed'))
    }
  }

  async function removeLogo() {
    if (await run(() => api('/organization/logo', { method: 'DELETE' }), 'Logo removed')) {
      reload()
      window.dispatchEvent(new Event('organization-changed'))
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <form onSubmit={save} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Organization details</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map(([key, text]) => (
              <div key={key} className={key === 'address' || key === 'report_footer' ? 'sm:col-span-2' : undefined}>
                <Field label={text}>
                  {key === 'timezone'
                    ? <TimezoneInput value={value(key)} onChange={(zone) => setDraft((d) => ({ ...d, timezone: zone }))} />
                    : <Input required={key === 'name'} value={value(key)} maxLength={key === 'address' ? 500 : key === 'currency' ? 8 : 160}
                      onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />}
                </Field>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><MapPin aria-hidden className="h-4 w-4 text-brand" /> Work area</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-ink-muted">People can check in and out, and record monitoring logs, only within this circle, at any of your locations. Leave it empty to allow it from anywhere.</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Latitude"><SignedNumberInput value={areaValue('latitude')} onChange={(v) => setArea((a) => ({ ...a, latitude: v }))} /></Field>
              <Field label="Longitude"><SignedNumberInput value={areaValue('longitude')} onChange={(v) => setArea((a) => ({ ...a, longitude: v }))} /></Field>
              <Field label="Radius (metres, 20 to 5000)"><Input inputMode="numeric" value={areaValue('radius')} onChange={(e) => setArea((a) => ({ ...a, radius: e.target.value.replace(/\D/g, '') }))} /></Field>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" onClick={useHere}>Use my current position</Button>
              {mapsLink && <Button asChild size="sm" variant="ghost"><a href={mapsLink} target="_blank" rel="noreferrer">Check on a map</a></Button>}
              <Button type="button" size="sm" variant="ghost" onClick={() => setArea({ latitude: '', longitude: '', radius: '' })}>Remove restriction</Button>
            </div>
          </CardContent>
        </Card>
        <Button type="submit" disabled={Object.keys(draft).length === 0 && Object.keys(area).length === 0}>Save organization</Button>
      </form>

      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Logo</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex h-28 items-center justify-center rounded-md border border-dashed border-border bg-surface-muted">
            {data.logo
              ? <img src={`/api/organization/logo?v=${version}`} alt="Organization logo" className="max-h-24 max-w-full object-contain" />
              : <span className="text-sm text-ink-muted">No logo yet</span>}
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-within:outline-2 focus-within:outline-brand">
              <Upload className="h-4 w-4" aria-hidden /> {data.logo ? 'Replace logo' : 'Upload logo'}
              <input type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(e) => { chooseLogo(e.target.files?.[0]); e.target.value = '' }} />
            </label>
            {data.logo && <Button variant="outline" onClick={removeLogo}><Trash2 className="h-4 w-4" /> Remove</Button>}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
