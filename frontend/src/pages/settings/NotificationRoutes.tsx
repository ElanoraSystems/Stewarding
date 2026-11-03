import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

interface Routes {
  categories: { key: string; label: string; about: string; default: string }[]
  roles: { name: string; label: string; tier: string }[]
  routes: Record<string, string[] | null>
}

/** Which roles are told about each kind of alert. A kind left on Default goes by role type, as before. */
export function NotificationRoutes() {
  const run = useRun()
  const { data, reload } = useApi<Routes>('/settings/notification-routes')
  const [draft, setDraft] = useState<Record<string, string[] | null>>({})
  if (!data) return null
  const value = (key: string) => (key in draft ? draft[key] : data.routes[key])
  const toggle = (key: string, role: string) => {
    const now = value(key) ?? []
    setDraft((d) => ({ ...d, [key]: now.includes(role) ? now.filter((r) => r !== role) : [...now, role] }))
  }

  async function save() {
    if (await run(() => api('/settings/notification-routes', { method: 'PUT', body: { routes: draft } }), 'Alert recipients saved')) {
      setDraft({})
      reload()
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Who gets which alerts</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        <p className="text-sm text-ink-muted">Choose the roles that are told about each kind of alert. People are told for the locations they work at; managers hear about every location. On Default, it goes by role type as before. A checklist can also be limited to job titles under Who sees it.</p>
        {data.categories.map((c) => {
          const chosen = value(c.key)
          return (
            <fieldset key={c.key} className="space-y-2 rounded-xl border border-border p-4">
              <legend className="px-2 text-sm font-semibold">{c.label} <span className="font-normal text-ink-muted">- {c.about}</span></legend>
              <div className="flex flex-wrap gap-2">
                <button type="button" aria-pressed={chosen === null} onClick={() => setDraft((d) => ({ ...d, [c.key]: null }))}
                  className={`rounded-full border px-3 py-1 text-sm font-medium ${chosen === null ? 'border-brand bg-brand text-brand-ink' : 'border-border text-ink-muted hover:bg-surface-muted'}`}>Default</button>
                {data.roles.map((r) => (
                  <button key={r.name} type="button" aria-pressed={chosen?.includes(r.name) ?? false} onClick={() => toggle(c.key, r.name)}
                    className={`rounded-full border px-3 py-1 text-sm font-medium ${chosen?.includes(r.name) ? 'border-brand bg-brand text-brand-ink' : 'border-border text-ink-muted hover:bg-surface-muted'}`}>{r.label}</button>
                ))}
              </div>
              <p className="text-xs text-ink-muted">{chosen === null ? `Default: ${c.default}` : chosen.length === 0 ? 'Nobody is told.' : `Told: ${chosen.map((n) => data.roles.find((r) => r.name === n)?.label ?? n).join(', ')}`}</p>
            </fieldset>
          )
        })}
        <Button disabled={Object.keys(draft).length === 0} onClick={save}>Save</Button>
      </CardContent>
    </Card>
  )
}
