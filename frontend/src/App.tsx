import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { useAuth } from '@/lib/auth'
import { AttendancePage } from '@/pages/AttendancePage'
import { AuditPage } from '@/pages/AuditPage'
import { BreakagePage } from '@/pages/BreakagePage'
import { ChecklistsPage } from '@/pages/ChecklistsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { EmployeesPage } from '@/pages/EmployeesPage'
import { EquipmentPage } from '@/pages/EquipmentPage'
import { InventoryPage } from '@/pages/InventoryPage'
import { LoginPage } from '@/pages/LoginPage'
import { ModulePage } from '@/pages/ModulePage'
import { ReportsPage } from '@/pages/ReportsPage'
import { RosterPage } from '@/pages/RosterPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { TasksPage } from '@/pages/TasksPage'
import { StockMovementsPage } from '@/pages/StockMovementsPage'
import { MonitoringPage } from '@/pages/MonitoringPage'

export default function App() {
  const { me, loading } = useAuth()
  if (loading) return <div className="p-8 text-sm text-ink-muted">Loading...</div>
  if (!me) return <LoginPage />

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="employees" element={<EmployeesPage />} />
        <Route path="attendance" element={<AttendancePage />} />
        <Route path="roster" element={<RosterPage />} />
        <Route path="daily-checklists" element={<ChecklistsPage frequency="daily" />} />
        <Route path="weekly-checklists" element={<ChecklistsPage frequency="weekly" />} />
        <Route path="monitoring" element={<MonitoringPage />} />
        <Route path="temperature" element={<Navigate to="/monitoring" replace />} />
        <Route path="equipment" element={<EquipmentPage />} />
        <Route path="inventory" element={me.modules.some((m) => m.key === 'inventory') ? <InventoryPage /> : <Navigate to="/" replace />} />
        <Route path="crockery" element={<Navigate to="/inventory" replace />} />
        <Route path="smallware" element={<Navigate to="/inventory" replace />} />
        <Route path="stock-movements" element={<StockMovementsPage />} />
        <Route path="breakage" element={<BreakagePage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path=":key" element={<ModulePage />} />
      </Route>
    </Routes>
  )
}
