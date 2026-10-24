import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { BrandMark } from '@/components/BrandMark'
import { APP_NAME } from '@/lib/brand'
import { useAuth } from '@/lib/auth'
import { useApi } from '@/lib/useApi'
import { api } from '@/lib/api'

export function LoginPage() {
  const { login } = useAuth()
  const org = useApi<{ name: string; has_logo: boolean }>('/organization/public')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [signingUp, setSigningUp] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (signingUp) {
        await api('/auth/signup', { body: { full_name: fullName, email, password } })
        setNotice('Request sent. You can sign in once a manager approves it.')
        setSigningUp(false)
        setPassword('')
      } else {
        setNotice(null)
        await login(email, password)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : signingUp ? 'Sign up failed' : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <BrandMark organization={org.data?.name ?? ''} hasLogo={org.data?.has_logo ?? false} />
          <CardTitle className="pt-2 text-xl">{signingUp ? 'Request an account' : `Sign in to ${APP_NAME}`}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {signingUp && (
              <label className="block space-y-1.5 text-sm font-medium">
                Full name
                <Input autoComplete="name" required minLength={2} value={fullName} onChange={(e) => setFullName(e.target.value)} />
              </label>
            )}
            <label className="block space-y-1.5 text-sm font-medium">
              Email
              <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="block space-y-1.5 text-sm font-medium">
              Password
              <PasswordInput
                autoComplete={signingUp ? 'new-password' : 'current-password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {notice && (
              <p role="status" className="rounded-md bg-ok/10 px-3 py-2 text-sm text-ok">
                {notice}
              </p>
            )}
            {error && (
              <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? 'Please wait...' : signingUp ? 'Request account' : 'Sign in'}
            </Button>
            <Button type="button" variant="ghost" className="w-full" onClick={() => { setSigningUp(!signingUp); setError(null); setNotice(null) }}>
              {signingUp ? 'Back to sign in' : 'New here? Request an account'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
