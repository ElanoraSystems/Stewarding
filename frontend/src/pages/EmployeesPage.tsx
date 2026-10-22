import { ArrowDown, ArrowUp, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FaceCapture, type FaceResult } from '@/components/FaceCapture'
import { Modal } from '@/components/ui/modal'
import { LocationSelect } from '@/components/LocationSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { Select } from '@/components/ui/select'
import { StatusBadge } from '@/components/ui/status-badge'
import { EmptyState, SkeletonRows, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Badge } from '@/components/ui/badge'
import { fmtDate, fmtDateTime } from '@/lib/format'
import { useRun } from '@/lib/toast'
import { qs, useApi } from '@/lib/useApi'
import { EmployeeForm, type EmployeeRow } from '@/pages/EmployeeForm'
import { ResetPasswordModal } from '@/pages/ResetPasswordModal'
import { useToast } from '@/lib/toast'

interface Listing {
  total: number
  items: EmployeeRow[]
}

const SIZE = 15
const COLUMNS = [
  ['employee_code', 'ID'],
  ['full_name', 'Name'],
  ['job_title', 'Job title'],
  ['status', 'Status'],
] as const

export function EmployeesPage() {
  const { me } = useAuth()
  const run = useRun()
  const canManage = me?.permissions.includes('employee.manage') ?? false
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [locationId, setLocationId] = useState<number | null>(null)
  const [sort, setSort] = useState('full_name')
  const [dir, setDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<EmployeeRow | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [toggling, setToggling] = useState<EmployeeRow | null>(null)
  const [resetting, setResetting] = useState<EmployeeRow | null>(null)
  const [enrolling, setEnrolling] = useState<EmployeeRow | null>(null)
  const toast = useToast()

  const { data, loading, reload } = useApi<Listing>(
    `/employees${qs({ search, status, location_id: locationId, sort, dir, page, size: SIZE })}`,
  )
  async function enroll(template: number[]): Promise<FaceResult> {
    try {
      await api(`/employees/${enrolling?.id}/face`, { body: { descriptor: template } })
      toast('ok', 'Face enrolled')
      setTimeout(() => { setEnrolling(null); reload() }, 1200)
      return { ok: true, message: 'Face enrolled' }
    } catch (err) {
      return { ok: false, message: err instanceof Error ? err.message : 'Could not save the face' }
    }
  }

  async function removeFace() {
    if (enrolling && await run(() => api(`/employees/${enrolling.id}/face`, { method: 'DELETE' }), 'Face removed')) {
      setEnrolling(null)
      reload()
    }
  }

  const { data: all } = useApi<Listing>(canManage ? '/employees?size=200' : null)
  const locationNames = new Map(me?.locations.map((l) => [l.id, l.code]))

  function sortBy(column: string) {
    setDir(sort === column && dir === 'asc' ? 'desc' : 'asc')
    setSort(column)
    setPage(1)
  }

  async function confirmToggle() {
    if (!toggling) return
    const action = toggling.status === 'active' ? 'deactivate' : 'activate'
    const ok = await run(() => api(`/employees/${toggling.id}/${action}`, { method: 'POST' }), `Employee ${action}d`)
    setToggling(null)
    if (ok) reload()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Employees</h1>
        {canManage && (
          <Button onClick={() => { setEditing(null); setFormOpen(true) }}>
            <Plus className="h-4 w-4" /> Add employee
          </Button>
        )}
      </div>

      <div className="filter-bar">
        <div className="relative min-w-52 flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-muted" aria-hidden />
          <Input aria-label="Search employees" className="pl-9" placeholder="Search name or ID" value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        </div>
        <Select aria-label="Status" className="w-auto" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </Select>
        <LocationSelect allowAll value={locationId} onChange={(id) => { setLocationId(id); setPage(1) }} />
      </div>

      <Table>
        <thead>
          <tr>
            {COLUMNS.map(([key, text]) => (
              <Th key={key} aria-sort={sort === key ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                <button type="button" className="inline-flex items-center gap-1" onClick={() => sortBy(key)}>
                  {text}
                  {sort === key && (dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                </button>
              </Th>
            ))}
            <Th>Locations</Th>
            {canManage && <Th>Joined</Th>}
            {canManage && <Th>Last sign-in</Th>}
            {canManage && <Th className="text-right">Actions</Th>}
          </tr>
        </thead>
        <tbody>
          {loading && !data ? <SkeletonRows cols={canManage ? 8 : 5} /> : data?.items.map((e) => (
            <tr key={e.id}>
              <Td>{e.employee_code}</Td>
              <Td className="font-medium">
                <span className="flex items-center gap-3">
                  <span aria-hidden className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand">{e.full_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()}</span>
                  {e.full_name}
                </span>
              </Td>
              <Td>{e.job_title}{e.company && <span className="block text-xs text-ink-muted">{e.company}</span>}</Td>
              <Td><StatusBadge status={e.status} /></Td>
              <Td>{e.location_ids.map((id) => locationNames.get(id) ?? id).join(', ')}</Td>
              {canManage && <Td>{fmtDate(e.date_joined)}</Td>}
              {canManage && (
                <Td>{e.account?.change_required ? <Badge tone="warn">Temporary password</Badge> : e.account?.last_login_at ? fmtDateTime(e.account.last_login_at) : 'Never'}</Td>
              )}
              {canManage && (
                <Td className="space-x-1.5 whitespace-nowrap text-right">
                  <Button size="sm" variant="outline" onClick={() => { setEditing(e); setFormOpen(true) }}>Edit</Button>
                  <Button size="sm" variant="outline" onClick={() => setEnrolling(e)}>{e.face_enrolled ? 'Update face' : 'Enroll face'}</Button>
                  {e.id !== me?.employee?.id && <Button size="sm" variant="outline" onClick={() => setResetting(e)}>Reset password</Button>}
                  <Button size="sm" variant={e.status === 'active' ? 'danger' : 'outline'} onClick={() => setToggling(e)}>
                    {e.status === 'active' ? 'Deactivate' : 'Activate'}
                  </Button>
                </Td>
              )}
            </tr>
          ))}
        </tbody>
      </Table>
      {data?.items.length === 0 && <EmptyState title="No employees found" />}
      {data && <Pagination page={page} size={SIZE} total={data.total} onPage={setPage} />}

      {formOpen && (
        <EmployeeForm open employee={editing} supervisors={(all?.items ?? []).filter((x) => x.role_tier !== 'steward')}
          onClose={() => setFormOpen(false)} onSaved={() => { setFormOpen(false); reload() }} />
      )}
      <Modal open={enrolling !== null} title={`Enroll face - ${enrolling?.full_name ?? ''}`} onClose={() => setEnrolling(null)}>
        <p className="mb-3 text-sm text-ink-muted">Only a numeric face template is stored, never a photo.</p>
        {enrolling && <FaceCapture onCapture={enroll} />}
        {enrolling?.face_enrolled && <div className="mt-3 text-right"><Button size="sm" variant="outline" onClick={removeFace}>Remove the face on file</Button></div>}
      </Modal>
      {resetting && <ResetPasswordModal employee={resetting} onClose={() => setResetting(null)} onDone={reload} />}
      <ConfirmDialog open={toggling !== null} title={toggling?.status === 'active' ? 'Deactivate employee' : 'Activate employee'}
        message={toggling?.status === 'active'
          ? `${toggling?.full_name} will no longer be able to sign in or check in.`
          : `${toggling?.full_name} will be able to sign in again.`}
        confirmLabel={toggling?.status === 'active' ? 'Deactivate' : 'Activate'}
        onConfirm={confirmToggle} onCancel={() => setToggling(null)} />
    </div>
  )
}
