import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DecisionDialog, type Decision } from '@/components/DecisionDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Pagination } from '@/components/ui/pagination'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, Skeleton, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime, label } from '@/lib/format'
import { ApprovalsTab, type Waiting } from '@/pages/ApprovalsTab'
import { PushToggle } from '@/components/PushToggle'
import { useRun, useToast } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { notificationsChanged } from '@/lib/notificationEvents'
import { needsAcknowledging, needsDecision, type Note } from '@/lib/notes'
import { NotificationList } from '@/pages/NotificationList'

interface PendingItem {
  category: string
  location: string
  urgency: string
  responsible: string
  description: string
  overdue_minutes: number
  link: string
}

interface Task {
  id: number
  description: string
  effective_status: string
  due_at: string | null
  local_date: string
}

const TABS = [['notifications', 'Notifications'], ['approvals', 'Approvals'], ['tasks', 'My tasks'], ['pending', 'Pending activities']] as const
/** The permissions of people who approve checklist tasks, readings, breakage or stock. */
const APPROVING = ['checklist.verify', 'temp.review', 'breakage.review', 'breakage.approve', 'stock.approve']
const SIZE = 15

function Notifications() {
  const { me } = useAuth()
  const run = useRun()
  const toast = useToast()
  const [view, setView] = useState<'all' | 'action' | 'unread'>('all')
  const [page, setPage] = useState(1)
  const { data, loading, reload } = useApi<{ total: number; unread: number; action_needed: number; items: Note[] }>(
    `/notifications${qs({ unread: view === 'unread', needs_action: view === 'action', page, size: SIZE })}`,
  )
  const places = new Map(me?.locations.map((l) => [l.id, l.name]))
  const [selected, setSelected] = useState<number[]>([])
  const [deciding, setDeciding] = useState<{ ids: number[]; initial: Decision } | null>(null)
  const [clearing, setClearing] = useState(false)
  // only people who approve work decide on alerts; someone who has to do the check just opens it
  const canDecide = APPROVING.some((p) => me?.permissions.includes(p))
  const decisions = canDecide ? (data?.items ?? []).filter(needsDecision) : []
  const warnings = canDecide ? (data?.items ?? []).filter(needsAcknowledging) : []
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  async function decide(decision: Decision, note: string) {
    if (!deciding) return false
    const result = await api<{ acknowledged: number }>('/notifications/acknowledge-many', { body: { ids: deciding.ids, decision, comment: note || null } }).catch((err) => {
      toast('error', err instanceof Error ? err.message : 'Could not save the decision')
      return null
    })
    if (!result) return false
    toast('ok', `${result.acknowledged} alert${result.acknowledged === 1 ? '' : 's'} ${decision}`)
    setDeciding(null)
    setSelected([])
    reload()
    notificationsChanged()
    return true
  }

  async function acknowledge(ids: number[]) {
    if (await run(() => api('/notifications/acknowledge-many', { body: { ids, decision: 'approved' } }), `${ids.length} acknowledged`)) {
      reload()
      notificationsChanged()
    }
  }

  async function clearAll() {
    const result = await api<{ cleared: number }>('/notifications/clear', { method: 'POST' }).catch(() => null)
    setClearing(false)
    if (result) {
      toast('ok', result.cleared ? `${result.cleared} notification${result.cleared === 1 ? '' : 's'} cleared` : 'Nothing to clear')
      setPage(1)
      reload()
      notificationsChanged()
    } else toast('error', 'Could not clear the notifications')
  }

  async function act(path: string, success?: string) {
    if (await run(() => api(`/notifications/${path}`, { method: 'POST' }), success)) {
      reload()
      notificationsChanged()
    }
  }

  return (
    <div className="space-y-3">
      <PushToggle />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
          {([['all', 'All'], ['action', `Needs action (${data?.action_needed ?? 0})`], ['unread', `Unread (${data?.unread ?? 0})`]] as const).map(([key, text]) => (
            <Button key={key} size="sm" variant={view === key ? 'default' : 'outline'} aria-pressed={view === key} onClick={() => { setView(key); setPage(1) }}>{text}</Button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => act('read-all', 'All marked as read')}>Mark all as read ({data?.unread ?? 0})</Button>
          <Button variant="outline" size="sm" disabled={(data?.total ?? 0) === 0} onClick={() => setClearing(true)}><Trash2 className="h-4 w-4" /> Clear notifications</Button>
        </div>
      </div>
      {(warnings.length > 0 || decisions.length > 0) && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm">
          <span>{warnings.length + decisions.length} alert{warnings.length + decisions.length === 1 ? '' : 's'} on this page need you</span>
          {warnings.length > 0 && <Button size="sm" onClick={() => acknowledge(warnings.map((n) => n.id))}>Acknowledge all ({warnings.length})</Button>}
          {decisions.length > 0 && <>
            <Button size="sm" variant="outline" onClick={() => setSelected(decisions.map((n) => n.id))}>Select requests</Button>
            <Button size="sm" disabled={selected.length === 0} onClick={() => setDeciding({ ids: selected, initial: 'approved' })}>Approve or reject selected ({selected.length})</Button>
          </>}
        </div>
      )}
      {loading && !data ? <Skeleton className="h-32 w-full" /> : data?.items.length === 0 ? <EmptyState title={view === 'action' ? 'Nothing needs your action' : 'No notifications'} /> : (
        <NotificationList items={data?.items ?? []} places={places} canDecide={canDecide} selected={selected} onToggle={toggle}
          onRead={(id) => act(`${id}/read`)} onAcknowledge={acknowledge} onDecide={(ids, initial) => setDeciding({ ids, initial })} />
      )}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}
      <DecisionDialog open={deciding !== null} initial={deciding?.initial} title={`Approve or reject ${deciding?.ids.length ?? 0} alert${deciding?.ids.length === 1 ? '' : 's'}`} onClose={() => setDeciding(null)} onDecide={decide} />
      <ConfirmDialog open={clearing} title="Clear notifications" message="This removes your notifications from the list. Alerts still waiting for your approval stay until you decide on them." confirmLabel="Clear" onConfirm={clearAll} onCancel={() => setClearing(false)} />
    </div>
  )
}

function MyTasks() {
  const { data, loading } = useApi<{ items: Task[] }>('/checklists/instances?mine=true&size=100')
  const open = (data?.items ?? []).filter((t) => !['completed', 'verified', 'waived', 'pending_verification'].includes(t.effective_status))
  if (loading && !data) return <Skeleton className="h-32 w-full" />
  if (open.length === 0) return <EmptyState title="No tasks assigned to you" />
  return (
    <ul className="space-y-2">
      {open.map((t) => (
        <li key={t.id}>
          <Link to="/checklists" className="flex items-center justify-between gap-2 rounded-lg border border-border bg-surface p-4 text-sm">
            <span><span className="block font-medium">{t.description}</span><span className="text-xs text-ink-muted">Due {fmtDateTime(t.due_at)}</span></span>
            <StatusBadge status={t.effective_status} />
          </Link>
        </li>
      ))}
    </ul>
  )
}

function Pending() {
  const { data, loading } = useApi<{ total: number; by_urgency: Record<string, number>; by_location: Record<string, Record<string, number>>; items: PendingItem[] }>('/notifications/pending-summary')
  if (loading && !data) return <Skeleton className="h-32 w-full" />
  if (!data || data.total === 0) return <EmptyState title="Nothing is pending" />
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge tone="critical">{data.by_urgency.critical} critical</Badge>
        <Badge tone="warn">{data.by_urgency.high} high</Badge>
        <Badge>{data.by_urgency.normal} normal</Badge>
        {Object.entries(data.by_location).map(([loc, c]) => <Badge key={loc}>{loc}: {c.critical + c.high + c.normal}</Badge>)}
      </div>
      <Table>
        <thead><tr><Th>Urgency</Th><Th>Location</Th><Th>Activity</Th><Th>Responsible</Th><Th className="text-right">Overdue</Th></tr></thead>
        <tbody>
          {data.items.map((i, n) => (
            <tr key={n}>
              <Td><Badge tone={i.urgency === 'critical' ? 'critical' : i.urgency === 'high' ? 'warn' : 'neutral'}>{i.urgency}</Badge></Td>
              <Td>{i.location}</Td>
              <Td><Link className="hover:underline" to={i.link}>{i.description}</Link><span className="ml-2 text-xs text-ink-muted">{label(i.category)}</span></Td>
              <Td>{i.responsible}</Td>
              <Td className="text-right tabular-nums">{i.overdue_minutes ? `${i.overdue_minutes} min` : '-'}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}

export function TasksPage() {
  const { me } = useAuth()
  const canSummary = me?.permissions.includes('report.view') ?? false
  const canApprove = ['checklist.verify', 'temp.review'].some((p) => me?.permissions.includes(p))  // the tab lists tasks and monitoring logs
  const waiting = useApi<Waiting>(canApprove ? '/approvals' : null)
  const tabs = TABS.filter(([key]) => (key !== 'pending' || canSummary) && (key !== 'approvals' || canApprove))
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('notifications')
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Tasks &amp; Notifications</h1>
      <div role="tablist" className="flex flex-wrap gap-2">
        {tabs.map(([key, text]) => (
          <Button key={key} role="tab" aria-selected={tab === key} size="sm" variant={tab === key ? 'default' : 'outline'} onClick={() => setTab(key)}>{text}{key === 'approvals' && waiting.data && waiting.data.count > 0 ? ` (${waiting.data.count})` : ''}</Button>
        ))}
      </div>
      {tab === 'notifications' && <Notifications />}
      {tab === 'approvals' && canApprove && <ApprovalsTab data={waiting.data ?? null} loading={waiting.loading} reload={() => { waiting.reload(); notificationsChanged() }} />}
      {tab === 'tasks' && <MyTasks />}
      {tab === 'pending' && canSummary && <Pending />}
    </div>
  )
}
