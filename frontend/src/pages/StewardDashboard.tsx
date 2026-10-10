import { AlertTriangle, ThermometerSun } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, Skeleton } from '@/components/ui/table'
import { fmtTime } from '@/lib/format'
import { useApi } from '@/lib/useApi'
import { MyShiftCard } from '@/pages/MyShiftCard'

interface StewardData {
  checked_in: boolean
  tasks: { total: number; done: number; overdue: number; outstanding: { id: number; description: string; status: string; due_at: string | null }[] }
  temperature_checks: { due: number; overdue: number }
  unresolved_issues: number
}

export function StewardDashboard() {
  const { data, loading, reload } = useApi<StewardData>('/dashboard')
  const percent = data && data.tasks.total ? Math.round((data.tasks.done / data.tasks.total) * 100) : 0

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">My shift today</h1>
        <p className="text-sm text-ink-muted">Your check-in, tasks and checks for this shift.</p>
      </div>

      <MyShiftCard onChange={reload} />

      {loading && !data ? <Skeleton className="h-40 w-full" /> : data && (
        <>
          {(data.temperature_checks.overdue > 0 || data.unresolved_issues > 0) && (
            <div role="alert" className="rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
              <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" aria-hidden /> Safety checks need you</p>
              <ul className="mt-1 list-inside list-disc">
                {data.temperature_checks.overdue > 0 && <li><Link className="underline" to="/temperature">{data.temperature_checks.overdue} temperature check(s) overdue</Link></li>}
                {data.unresolved_issues > 0 && <li><Link className="underline" to="/temperature">{data.unresolved_issues} failed reading(s) still open</Link></li>}
              </ul>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Checklist progress
                <span className="text-sm font-normal text-ink-muted">{data.tasks.done} of {data.tasks.total} done</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="h-2 overflow-hidden rounded bg-border" role="img" aria-label={`${percent}% of tasks done`}>
                <div className="h-full bg-brand" style={{ width: `${percent}%` }} />
              </div>
              {data.tasks.outstanding.length === 0 ? <EmptyState title="All tasks are done" hint="Nice work." /> : (
                <ul className="divide-y divide-border">
                  {data.tasks.outstanding.map((t) => (
                    <li key={t.id}>
                      <Link to="/daily-checklists" className="flex items-center justify-between gap-2 py-3 text-sm">
                        <span><span className="block font-medium">{t.description}</span><span className="text-xs text-ink-muted">Due {fmtTime(t.due_at)}</span></span>
                        <StatusBadge status={t.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Link to="/temperature" className="block">
            <Card className={data.temperature_checks.overdue ? 'border-danger/50' : undefined}>
              <CardContent className="flex items-center justify-between gap-3 py-4">
                <span className="flex items-center gap-2 font-medium"><ThermometerSun className="h-5 w-5 text-brand" aria-hidden /> Temperature checks</span>
                <span className="flex gap-2">
                  <Badge tone={data.temperature_checks.due ? 'warn' : 'neutral'}>{data.temperature_checks.due} due</Badge>
                  <Badge tone={data.temperature_checks.overdue ? 'critical' : 'neutral'}>{data.temperature_checks.overdue} overdue</Badge>
                </span>
              </CardContent>
            </Card>
          </Link>
        </>
      )}
    </div>
  )
}
