import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { greeting, HeroCard } from '@/components/HeroCard'
import { Skeleton } from '@/components/ui/table'
import { useAuth } from '@/lib/auth'
import { fmtTime } from '@/lib/format'
import { useApi } from '@/lib/useApi'
import { MyShiftCard } from '@/pages/MyShiftCard'
import { MyWorkList, type MyWork } from '@/pages/MyWorkList'

interface StewardData {
  sections?: string[]
  checked_in: boolean
  check_in_at?: string | null
  tasks: { total: number; done: number; overdue: number; outstanding: { id: number; description: string; status: string; due_at: string | null }[] }
  monitoring_checks: { due: number; overdue: number }
  unresolved_issues: number
}

export function StewardDashboard() {
  const { me } = useAuth()
  const { data, reload } = useApi<StewardData>('/dashboard')
  const work = useApi<MyWork>('/dashboard/my-work')
  const shows = (part: string) => !data?.sections || data.sections.includes(part)  // older answers carry no list: show everything

  const shift = <MyShiftCard onChange={() => { reload(); work.reload() }} />
  const list = work.loading && !work.data ? <Skeleton className="h-40 w-full" /> : work.data && (
    <MyWorkList work={work.data} timezoneOf={(id) => me?.locations.find((l) => l.id === id)?.timezone} showPlace={(me?.locations.length ?? 0) > 1} />
  )

  return (
    <div className="space-y-4">
      <HeroCard
        eyebrow={new Intl.DateTimeFormat('en-GB', { dateStyle: 'full' }).format(new Date())}
        title={`${greeting()}, ${(me?.employee?.name ?? '').split(' ')[0] || 'there'}`}
        chips={data ? [
          data.checked_in ? { label: `On duty since ${fmtTime(data.check_in_at)}` } : { label: 'Not checked in', urgent: true },
          ...(shows('checklists') ? [{ label: `${data.tasks.done} of ${data.tasks.total} tasks done` }] : []),
          ...(shows('checklists') && data.tasks.overdue > 0 ? [{ label: `${data.tasks.overdue} overdue`, urgent: true }] : []),
          ...(shows('monitoring') && data.monitoring_checks.due > 0 ? [{ label: `${data.monitoring_checks.due} checks due` }] : []),
        ] : []}
      />

      {/* on duty: the list comes first, the card below it; not yet in: the big Check in button comes first */}
      {data?.checked_in ? <>{list}{shift}</> : <>{shift}{list}</>}

      {data && shows('monitoring') && data.unresolved_issues > 0 && (
        <div role="alert" className="rounded-xl border border-danger/20 border-l-4 border-l-danger bg-danger-soft px-4 py-3 text-sm text-danger">
          <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" aria-hidden /> Safety checks need you</p>
          <p className="mt-1"><Link className="underline" to="/monitoring">{data.unresolved_issues} failed check(s) still open</Link></p>
        </div>
      )}
    </div>
  )
}
