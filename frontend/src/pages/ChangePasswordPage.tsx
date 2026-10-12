import { useState, type FormEvent } from 'react'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'

const RULES = 'At least 10 characters, using at least two kinds: letters, numbers or symbols. It must not contain your sign-in name.'

export function ChangePasswordPage({ forced = false }: { forced?: boolean }) {
  const { me, changePassword, logout } = useAuth()
  const run = useRun()
  const org = useApi<{ name: string; has_logo: boolean }>(forced ? '/organization/public' : null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const mismatch = again !== '' && again !== next

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (mismatch) return
    if (await run(() => changePassword(current, next), 'Password changed')) {
      setCurrent('')
      setNext('')
      setAgain('')
    }
  }

  const card = (
    <Card className="w-full max-w-md">
      <CardHeader>
        {forced && <BrandMark organization={org.data?.name ?? ''} hasLogo={org.data?.has_logo ?? false} />}
        <CardTitle className="pt-1 text-xl">{forced ? 'Choose your own password' : 'Change password'}</CardTitle>
        <p className="text-sm text-ink-muted">
          {forced ? 'You are using a temporary password. Choose one only you know to continue.' : `Signed in as ${me?.email}. Changing it signs you out of other devices.`}
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Field label={forced ? 'Temporary password' : 'Current password'}>
            <Input required type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="New password" hint={RULES}>
            <Input required type="password" minLength={10} maxLength={128} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="Repeat the new password">
            <Input required type="password" autoComplete="new-password" aria-invalid={mismatch} value={again} onChange={(e) => setAgain(e.target.value)} />
          </Field>
          {mismatch && <p role="alert" className="text-sm text-danger">The two passwords do not match.</p>}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={mismatch || !current || next.length < 10}>Save new password</Button>
            {forced && <Button type="button" variant="outline" onClick={logout}>Sign out</Button>}
          </div>
        </form>
      </CardContent>
    </Card>
  )
  return forced ? <div className="flex min-h-screen items-center justify-center p-4">{card}</div> : <div className="flex justify-center pt-4">{card}</div>
}
