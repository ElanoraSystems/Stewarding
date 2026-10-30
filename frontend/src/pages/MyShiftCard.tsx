import { LogIn, LogOut } from 'lucide-react'
import { useRef, useState } from 'react'
import { LocationSelect } from '@/components/LocationSelect'
import { FaceCapture, type FaceEvidence, type FaceResult } from '@/components/FaceCapture'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/table'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type { Step } from '@/lib/face'
import { fmtTime } from '@/lib/format'
import { currentPosition } from '@/lib/geo'
import { useToast } from '@/lib/toast'
import { useApi } from '@/lib/useApi'
import { useTick } from '@/lib/useTick'
import { cn } from '@/lib/utils'
import { Overlay, Problem, ProgressRing, Summary, Welcome, type ProblemKind } from '@/pages/CheckInParts'

interface ShiftStatus {
  checked_in: boolean
  server_time: string
  employee: string
  employee_code: string
  record: { check_in_at: string; late_minutes: number } | null
  location?: { id: number; name: string; timezone: string; geofence: boolean }
  shift?: string
  incomplete_task_count: number
  face_required: boolean
  face_enrolled: boolean
  rostered_today: { location_id: number; location_name: string; shift: string; start: string; end: string; week_off: boolean }[]
}

interface Challenge {
  token: string
  steps: Step[]
}

interface Done {
  check_in_at: string
  late_minutes: number
}

type Trouble = { kind: ProblemKind; detail?: string; retry: () => void } | null

const clock = (seconds: number) => `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
const minutesOf = (text: string) => {
  const [h, m] = text.split(':').map(Number)
  return h * 60 + (m || 0)
}
/** True for the messages that mean the position, not the person, was the problem. */
const isLocationError = (message: string) => /\bm from\b|imprecise|location access|location could not|share its location/i.test(message)

export function MyShiftCard({ onChange }: { onChange?: () => void }) {
  const toast = useToast()
  const { data, loading, reload } = useApi<ShiftStatus>('/attendance/me/status')
  const [picked, setPicked] = useState<number | null>(null)
  const [elsewhere, setElsewhere] = useState(false)
  const rostered = data?.rostered_today ?? []
  const working = rostered.filter((r) => !r.week_off)
  const locationId = picked ?? working[0]?.location_id ?? null
  const locked = new Set(working.map((r) => r.location_id)).size === 1 && !elsewhere
  const { me } = useAuth()
  const byLocation = me?.by_location !== false
  // without a chosen location the server finds the one the position fits, so send the position when any of mine has a boundary
  const fencedFor = (id: number | null) => (byLocation ? me?.locations.find((l) => l.id === id)?.geofence : me?.locations.some((l) => l.geofence))
  const placeFor = (id: number | null) => (byLocation ? { location_id: id } : {})
  const [exceptionOpen, setExceptionOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [faceFor, setFaceFor] = useState<'in' | 'out' | null>(null)
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [trouble, setTrouble] = useState<Trouble>(null)
  const [welcome, setWelcome] = useState<{ time: string; place: string | null; late: number } | null>(null)
  const [summary, setSummary] = useState<{ worked: string; inTime: string; outTime: string; openTasks: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const proof = useRef<Record<string, unknown> | null>(null)
  const now = useTick(!!data?.checked_in)

  const refresh = () => {
    reload()
    onChange?.()
  }

  async function newChallenge(direction: 'in' | 'out') {
    const made = await api<{ required: boolean; token?: string; steps?: Step[] }>('/attendance/face-challenge', { body: { action: direction } })
    setChallenge(made.required && made.token && made.steps ? { token: made.token, steps: made.steps } : null)
  }

  async function needFace(direction: 'in' | 'out') {
    if (!data?.face_enrolled) {
      setTrouble({ kind: 'unenrolled', retry: () => setTrouble(null) })
      return
    }
    try {
      await newChallenge(direction)
      setFaceFor(direction)
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Could not start the camera check')
    }
  }

  const placeName = () => (byLocation ? me?.locations.find((l) => l.id === locationId)?.name ?? null : null)

  function checkedIn(done: Done) {
    setWelcome({ time: fmtTime(done.check_in_at), place: placeName(), late: done.late_minutes })
    refresh()
  }

  function checkedOut() {
    const start = data?.record ? new Date(data.record.check_in_at).getTime() : Date.now()
    const end = Date.now()
    const minutes = Math.max(0, Math.round((end - start) / 60000))
    setSummary({ worked: `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`, inTime: fmtTime(new Date(start).toISOString()), outTime: fmtTime(new Date(end).toISOString()), openTasks: data?.incomplete_task_count ?? 0 })
    proof.current = null
    setExceptionOpen(false)
    setReason('')
    refresh()
  }

  async function verifyFace(template: number[], evidence: FaceEvidence): Promise<FaceResult> {
    const direction = faceFor
    const faceBody = { face: template, ...(challenge ? { challenge: challenge.token, liveness: evidence.liveness, snapshot: evidence.snapshot } : {}) }
    try {
      if (direction === 'in') {
        const fenced = fencedFor(locationId)
        const done = await api<Done>('/attendance/check-in', { body: { ...placeFor(locationId), ...faceBody, ...(fenced ? await currentPosition() : {}) } })
        setTimeout(() => { setFaceFor(null); checkedIn(done) }, 900)
      } else {
        const where = data?.location?.geofence ? await currentPosition() : {}
        await api('/attendance/check-out', { body: { ...faceBody, ...where } })
        setTimeout(() => { setFaceFor(null); checkedOut() }, 900)
      }
      return { ok: true, message: 'Match found!' }
    } catch (err) {
      if (direction === 'out' && err instanceof ApiError && err.status === 409 && typeof err.detail === 'object') {
        proof.current = faceBody
        setFaceFor(null)
        setExceptionOpen(true)
        return { ok: true, message: 'Match found!' }
      }
      const message = err instanceof Error ? err.message : 'Could not verify your face'
      if (isLocationError(message)) {
        // the face matched; only the position is wrong, so leave the camera and say so
        setFaceFor(null)
        setTrouble({ kind: 'location', detail: message, retry: () => { setTrouble(null); void (direction === 'out' ? needFace('out') : needFace('in')) } })
        return { ok: true, message: 'Match found!' }
      }
      if (direction) await newChallenge(direction).catch(() => undefined)
      return { ok: false, message }
    }
  }

  async function checkIn() {
    if (byLocation && locationId === null) return
    if (data?.face_required) return needFace('in')
    setBusy(true)
    try {
      const done = await api<Done>('/attendance/check-in', { body: { ...placeFor(locationId), ...(fencedFor(locationId) ? await currentPosition() : {}) } })
      checkedIn(done)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Check-in failed'
      if (isLocationError(message)) setTrouble({ kind: 'location', detail: message, retry: () => { setTrouble(null); void checkIn() } })
      else toast('error', message)
    } finally {
      setBusy(false)
    }
  }

  async function checkOut(withReason?: string) {
    setBusy(true)
    try {
      const where = data?.location?.geofence ? await currentPosition() : {}
      await api('/attendance/check-out', { body: { exception_reason: withReason ?? null, ...(proof.current ?? {}), ...where } })
      checkedOut()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Check-out failed'
      if (err instanceof ApiError && err.status === 409 && typeof err.detail === 'object') setExceptionOpen(true)
      else if (isLocationError(message)) setTrouble({ kind: 'location', detail: message, retry: () => { setTrouble(null); void checkOut(withReason) } })
      else toast('error', message)
    } finally {
      setBusy(false)
    }
  }

  if (loading && !data) return <Skeleton className="h-40 w-full" />
  if (!data) return null

  const fenced = fencedFor(locationId)
  const rosterHere = working.find((r) => r.location_id === (data.location?.id ?? locationId))
  const planned = rosterHere ? ((minutesOf(rosterHere.end) - minutesOf(rosterHere.start) + 1440) % 1440 || 1440) : 480
  const elapsed = data.record ? Math.max(0, Math.floor((now - new Date(data.record.check_in_at).getTime()) / 1000)) : 0
  const disabled = byLocation && locationId === null

  return (
    <Card className="overflow-hidden rounded-3xl shadow-lg">
      <div className="bg-hero-b bg-gradient-to-br from-hero-a to-hero-b px-6 pb-7 pt-6 text-white">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-lg font-semibold">{data.employee}</p>
            <p className="text-sm text-white/80">{data.employee_code}</p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3.5 py-1.5 text-sm font-semibold">
            <span aria-hidden className={cn('h-2 w-2 rounded-full', data.checked_in ? 'ci-breathe bg-[#7fd6c2]' : 'bg-[#f2b45e]')} />
            {data.checked_in ? 'On duty' : 'Not checked in'}
          </span>
        </div>
        {data.checked_in && data.record && (
          <div className="mt-5">
            <ProgressRing progress={elapsed / (planned * 60)}>
              <p className="text-4xl font-bold tabular-nums tracking-tight">{clock(elapsed)}</p>
              <p className="mt-0.5 text-sm text-white/85">since {fmtTime(data.record.check_in_at, data.location?.timezone)}</p>
            </ProgressRing>
          </div>
        )}
      </div>

      <div className="space-y-6 p-6">
        {data.checked_in && data.record && data.location ? (
          <>
            <p className="text-base">Checked in at <span className="font-semibold">{fmtTime(data.record.check_in_at, data.location.timezone)}</span>{byLocation && <> at {data.location.name}</>}.</p>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-2xl bg-surface-muted/70 p-4"><dt className="text-ink-muted">Shift</dt><dd className="text-base font-semibold">{data.shift ?? 'Unscheduled'}</dd></div>
              <div className="rounded-2xl bg-surface-muted/70 p-4"><dt className="text-ink-muted">Open tasks</dt><dd className="text-base font-semibold">{data.incomplete_task_count}</dd></div>
            </dl>
            {data.record.late_minutes > 0 && <Badge tone="warn">Checked in {data.record.late_minutes} min late</Badge>}
            <Button className="ci-press h-14 w-full rounded-2xl bg-side text-base font-bold text-white hover:bg-side/90" disabled={busy} onClick={() => (data.face_required ? needFace('out') : checkOut())}>
              <LogOut className="h-5 w-5" /> Check out
            </Button>
          </>
        ) : (
          <>
            <div className="space-y-1 rounded-2xl bg-surface-muted/70 px-4 py-3 text-sm">
              <p className="font-medium">Today</p>
              {rostered.length === 0 ? <p className="text-ink-muted">You are not on the roster today.</p> : rostered.map((r) => (
                <p key={`${r.location_id}-${r.shift}`} className="text-ink-muted">
                  {r.week_off ? <>Week off{byLocation && <> at {r.location_name}</>}</> : <>{r.shift}, {r.start} to {r.end}{byLocation && <>, at <span className="font-medium text-ink">{r.location_name}</span></>}</>}
                </p>
              ))}
            </div>
            {!byLocation ? null : locked ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">Where are you working?</p>
                <p className="flex min-h-12 items-center rounded-xl border border-border bg-surface-muted px-3 text-base font-medium">{working[0].location_name} (rostered today)</p>
                <button type="button" className="min-h-11 text-sm font-medium text-brand-deep hover:underline" onClick={() => setElsewhere(true)}>Working somewhere else?</button>
              </div>
            ) : (
              <Field label="Where are you working?"><LocationSelect className="h-12 w-full text-base" value={locationId} preferred={working.map((r) => r.location_id)} onChange={setPicked} /></Field>
            )}
            <div className="flex flex-col items-center py-2">
              <div className="relative h-44 w-44">
                {!disabled && <>
                  <span aria-hidden className="ci-pulse absolute inset-0 rounded-full bg-brand" />
                  <span aria-hidden className="ci-pulse absolute inset-0 rounded-full bg-brand [animation-delay:1.2s]" />
                </>}
                <button type="button" aria-label="Check in" disabled={disabled || busy} onClick={checkIn}
                  className="ci-press absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-full bg-hero-b bg-gradient-to-br from-[#138572] to-hero-b text-xl font-bold text-white shadow-xl shadow-brand/40 disabled:from-ink-muted disabled:to-ink-muted disabled:shadow-none">
                  <LogIn className="h-9 w-9" aria-hidden />
                  Check in
                </button>
              </div>
              {(data.face_required || fenced) && (
                <p className="mt-5 max-w-xs text-center text-sm text-ink-muted">{data.face_required ? 'A quick face check runs next.' : 'Your location is checked next.'}</p>
              )}
            </div>
          </>
        )}
      </div>

      {faceFor !== null && (
        <Overlay label={faceFor === 'in' ? 'Check in with your face' : 'Check out with your face'}>
          <p className="text-2xl font-bold">Face check</p>
          <p className="mt-1 text-center text-[15px] text-white/85">Hold your phone at eye level and follow the steps.</p>
          <div className="mt-8">
            <FaceCapture round steps={challenge?.steps} onCapture={verifyFace} onBlocked={() => { const d = faceFor; setFaceFor(null); setTrouble({ kind: 'blocked', retry: () => { setTrouble(null); void needFace(d) } }) }} />
          </div>
          <button type="button" onClick={() => setFaceFor(null)} className="mt-auto min-h-12 px-5 text-[15px] font-semibold text-white underline">Cancel</button>
        </Overlay>
      )}

      {welcome && <Welcome time={welcome.time} place={welcome.place} late={welcome.late} onContinue={() => setWelcome(null)} />}
      {summary && <Summary {...summary} onDone={() => setSummary(null)} />}
      {trouble && <Problem kind={trouble.kind} detail={trouble.detail} onRetry={trouble.retry} onBack={() => setTrouble(null)} />}

      {exceptionOpen && (
        <div role="dialog" aria-modal="true" aria-label="Tasks still open" className="fixed inset-0 z-50">
          <div className="ci-fade absolute inset-0 bg-side/60" onClick={() => setExceptionOpen(false)} aria-hidden />
          <div className="ci-slide-up absolute inset-x-0 bottom-0 mx-auto max-w-md rounded-t-[28px] bg-surface p-6 pb-8 shadow-2xl">
            <span aria-hidden className="mx-auto mb-4 block h-1.5 w-11 rounded-full bg-border" />
            <h2 className="text-2xl font-bold">Tasks still open</h2>
            <p className="mb-4 mt-1.5 text-[15px] leading-snug text-ink-muted">{data.incomplete_task_count} mandatory task(s) not finished. Say why you are leaving. Your manager will see the reason.</p>
            <Field label="Reason">
              <Input value={reason} onChange={(e) => setReason(e.target.value)} className="h-12 text-base" />
            </Field>
            <div className="mt-5 flex gap-3">
              <Button variant="outline" className="h-12 flex-1 rounded-2xl font-bold" onClick={() => setExceptionOpen(false)}>Go back</Button>
              <Button variant="danger" className="h-12 flex-1 rounded-2xl font-bold" disabled={reason.trim().length < 5 || busy} onClick={() => checkOut(reason)}>Check out with reason</Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
