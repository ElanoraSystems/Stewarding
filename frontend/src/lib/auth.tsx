import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, tokenStore } from '@/lib/api'

export interface Me {
  id: number
  email: string
  change_required: boolean
  role: 'manager' | 'supervisor' | 'steward'
  employee: { id: number; name: string; code: string } | null
  permissions: string[]
  locations: { id: number; code: string; name: string; timezone: string; geofence: boolean }[]
  modules: { key: string; label: string }[]
}

interface AuthState {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
  refresh: () => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(Boolean(tokenStore.get()))

  const logout = useCallback(() => {
    tokenStore.clear()
    setMe(null)
  }, [])

  useEffect(() => {
    if (!tokenStore.get()) return
    api<Me>('/auth/me')
      .then(setMe)
      .catch(logout)
      .finally(() => setLoading(false))
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api<{ access_token: string }>('/auth/login', { body: { email, password } })
    tokenStore.set(access_token)
    setMe(await api<Me>('/auth/me'))
  }, [])

  const changePassword = useCallback(async (current: string, next: string) => {
    const { access_token } = await api<{ access_token: string }>('/auth/change-password', { body: { current_password: current, new_password: next } })
    tokenStore.set(access_token)
    setMe(await api<Me>('/auth/me'))
  }, [])

  /** Reloads the signed-in user, so new locations and changed access show up without signing in again. */
  const refresh = useCallback(async () => {
    setMe(await api<Me>('/auth/me'))
  }, [])

  const value = useMemo(() => ({ me, loading, login, changePassword, refresh, logout }), [me, loading, login, changePassword, refresh, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
