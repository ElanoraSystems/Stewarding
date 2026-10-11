import type { Schedule } from '@/pages/MonitoringRecordForm'

/** Checks of one monitoring point that fall due together, such as wash and rinse, so they are recorded in one go. */
export function cycleOf(schedule: Schedule, all: Schedule[]): Schedule[] {
  const key = (s: Schedule) => [s.timing, s.time_of_day, s.interval_minutes, s.weekdays.join(), s.day_of_month].join('|')
  return all.filter((s) => s.active && key(s) === key(schedule))
}
