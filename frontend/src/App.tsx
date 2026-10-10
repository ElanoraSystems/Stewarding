import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { useAuth } from '@/lib/auth'
import { DashboardPage } from '@/pages/DashboardPage'
import { LoginPage } from '@/pages/LoginPage'
import { ModulePage } from '@/pages/ModulePage'

export default function App() {
  const { me, loading } = useAuth()
  if (loading) return <div className="p-8 text-sm text-ink-muted">Loading...</div>
  if (!me) return <LoginPage />

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path=":key" element={<ModulePage />} />
      </Route>
    </Routes>
  )
}
