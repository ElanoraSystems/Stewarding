import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { useAuth } from '@/lib/auth'
import { AttendancePage } from '@/pages/AttendancePage'
import { BreakagePage } from '@/pages/BreakagePage'
import { ChecklistsPage } from '@/pages/ChecklistsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { EmployeesPage } from '@/pages/EmployeesPage'
import { EquipmentPage } from '@/pages/EquipmentPage'
import { InventoryPage } from '@/pages/InventoryPage'
import { LoginPage } from '@/pages/LoginPage'
import { ModulePage } from '@/pages/ModulePage'
import { RosterPage } from '@/pages/RosterPage'
import { StockMovementsPage } from '@/pages/StockMovementsPage'
import { TemperaturePage } from '@/pages/TemperaturePage'

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
        <Route path="temperature" element={<TemperaturePage />} />
        <Route path="equipment" element={<EquipmentPage />} />
        <Route path="crockery" element={<InventoryPage kind="crockery" />} />
        <Route path="smallware" element={<InventoryPage kind="smallware" />} />
        <Route path="stock-movements" element={<StockMovementsPage />} />
        <Route path="breakage" element={<BreakagePage />} />
        <Route path=":key" element={<ModulePage />} />
      </Route>
    </Routes>
  )
}
