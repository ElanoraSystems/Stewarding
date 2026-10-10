import { EquipmentPage } from '@/pages/EquipmentPage'

/** Monitoring schedules are edited per machine, so this tab reuses the equipment editor. */
export function SettingsMonitoring() {
  return <EquipmentPage embedded />
}
