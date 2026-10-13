import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRun } from '@/lib/toast'
import { useLookup } from '@/lib/useLookups'

export interface EmployeeRow {
  id: number
  employee_code: string
  full_name: string
  job_title: string
  status: string
  supervisor_id: number | null
  location_ids: number[]
  role: string | null
  phone?: string | null
  email?: string | null
  emergency_contact?: string | null
  date_joined?: string | null
  account?: { change_required: boolean; last_login_at: string | null } | null
}

interface EmployeeFormProps {
  open: boolean
  employee: EmployeeRow | null
  supervisors: EmployeeRow[]
  onClose: () => void
  onSaved: () => void
}

export function EmployeeForm({ open, employee, supervisors, onClose, onSaved }: EmployeeFormProps) {
  const { me } = useAuth()
  const run = useRun()
  const titles = useLookup('job_title')
  const editing = employee !== null
  const [form, setForm] = useState({
    employee_code: employee?.employee_code ?? '',
    full_name: employee?.full_name ?? '',
    job_title: employee?.job_title ?? 'Steward',
    email: employee?.email ?? '',
    password: '',
    role: employee?.role ?? 'steward',
    phone: employee?.phone ?? '',
    emergency_contact: employee?.emergency_contact ?? '',
    date_joined: employee?.date_joined ?? '',
    supervisor_id: employee?.supervisor_id ? String(employee.supervisor_id) : '',
    location_ids: employee?.location_ids ?? [],
  })
  const [busy, setBusy] = useState(false)
  const set = (key: keyof typeof form, value: string | number[]) => setForm((f) => ({ ...f, [key]: value }))

  function toggleLocation(id: number) {
    set('location_ids', form.location_ids.includes(id) ? form.location_ids.filter((i) => i !== id) : [...form.location_ids, id])
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    const common = {
      full_name: form.full_name,
      job_title: form.job_title,
      role: form.role,
      ...(editing ? { email: form.email } : {}),
      phone: form.phone || null,
      emergency_contact: form.emergency_contact || null,
      date_joined: form.date_joined || null,
      supervisor_id: form.supervisor_id ? Number(form.supervisor_id) : null,
      location_ids: form.location_ids,
    }
    const ok = await run(
      () =>
        editing
          ? api(`/employees/${employee.id}`, { method: 'PUT', body: common })
          : api('/employees', { body: { ...common, employee_code: form.employee_code, email: form.email, password: form.password } }),
      editing ? 'Employee updated' : 'Employee created',
    )
    setBusy(false)
    if (ok) onSaved()
  }

  return (
    <Modal open={open} title={editing ? 'Edit employee' : 'Add employee'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        {!editing && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employee ID">
              <Input required value={form.employee_code} onChange={(e) => set('employee_code', e.target.value)} />
            </Field>
            <Field label="Email">
              <Input required type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
            </Field>
          </div>
        )}
        {editing && (
          <Field label="Email (their sign-in)" hint="Correct a typo here. They sign in with the new address straight away.">
            <Input required type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
          </Field>
        )}
        <Field label="Full name">
          <Input required value={form.full_name} onChange={(e) => set('full_name', e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Job title">
            <Input required list="job-titles" value={form.job_title} onChange={(e) => set('job_title', e.target.value)} />
            <datalist id="job-titles">{titles.map((t) => <option key={t} value={t} />)}</datalist>
          </Field>
          <Field label="Role">
            <Select value={form.role} onChange={(e) => set('role', e.target.value)}>
              <option value="steward">Steward</option>
              <option value="supervisor">Stewarding Supervisor</option>
              <option value="manager">Back of House Manager</option>
            </Select>
          </Field>
        </div>
        {!editing && (
          <Field label="Initial password" hint="At least 10 characters with two kinds of characters. They are asked to choose their own at first sign-in.">
            <Input required type="password" minLength={10} autoComplete="new-password" value={form.password} onChange={(e) => set('password', e.target.value)} />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Phone">
            <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} />
          </Field>
          <Field label="Date of joining">
            <Input type="date" value={form.date_joined} onChange={(e) => set('date_joined', e.target.value)} />
          </Field>
        </div>
        <Field label="Emergency contact">
          <Input value={form.emergency_contact} onChange={(e) => set('emergency_contact', e.target.value)} />
        </Field>
        <Field label="Supervisor">
          <Select value={form.supervisor_id} onChange={(e) => set('supervisor_id', e.target.value)}>
            <option value="">None</option>
            {supervisors.filter((s) => s.id !== employee?.id).map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name}
              </option>
            ))}
          </Select>
        </Field>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Assigned locations</legend>
          {me?.locations.map((location) => (
            <label key={location.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.location_ids.includes(location.id)} onChange={() => toggleLocation(location.id)} />
              {location.name}
            </label>
          ))}
          {form.location_ids.length === 0 && <p className="text-xs text-warn">Choose at least one location before saving.</p>}
        </fieldset>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || form.location_ids.length === 0}>
            {busy ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
