import { useAuth } from '@/lib/auth'
import { ManagerDashboard } from '@/pages/ManagerDashboard'
import { StewardDashboard } from '@/pages/StewardDashboard'

export function DashboardPage() {
  const { me } = useAuth()
  if (!me) return null
  return me.tier === 'steward' ? <StewardDashboard /> : <ManagerDashboard />
}
