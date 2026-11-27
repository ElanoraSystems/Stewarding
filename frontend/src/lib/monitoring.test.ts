import { describe, expect, it } from 'vitest'
import { cycleOf } from './monitoring'
import type { Schedule } from '@/pages/MonitoringRecordForm'

const check = (id: number, phase: Schedule['phase'], max_open_minutes: number | null) =>
  ({ id, active: true, phase, timing: 'checkpoint', time_of_day: null, interval_minutes: null, weekdays: [], day_of_month: null, max_open_minutes }) as unknown as Schedule

describe('cycleOf', () => {
  it('records the stages of a cooling log one at a time, each with its own deadline', () => {
    const all = [check(1, 'start', null), check(2, 'finish', 120), check(3, 'finish', 360)]
    expect(cycleOf(all[1], all).map((s) => s.id)).toEqual([2])
    expect(cycleOf(all[2], all).map((s) => s.id)).toEqual([3])
  })

  it('keeps the time out checks of a defrosting log together', () => {
    const all = [check(1, 'finish', null), check(2, 'finish', null)]
    expect(cycleOf(all[0], all).map((s) => s.id)).toEqual([1, 2])
  })
})
