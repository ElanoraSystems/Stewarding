import { CameraOff, Check, MapPin, UserX, type LucideIcon } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** A whole-screen layer for the check-in steps, so the person sees one thing at a time. */
export function Overlay({ label, tone = 'dark', children }: { label: string; tone?: 'dark' | 'brand' | 'light'; children: ReactNode }) {
  return (
    <div role="dialog" aria-modal="true" aria-label={label}
      className={cn('ci-fade fixed inset-0 z-50 flex flex-col items-center overflow-y-auto px-6 pb-8 pt-14 text-white',
        tone === 'dark' && 'bg-gradient-to-br from-side to-hero-b', tone === 'brand' && 'bg-gradient-to-br from-hero-a to-hero-b', tone === 'light' && 'bg-page text-ink')}>
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center">{children}</div>
    </div>
  )
}

const CONFETTI = [
  ['6%', '#f2b45e', '0.1s', '2.6s'], ['16%', '#ffffff', '0.4s', '3s'], ['27%', '#7fd6c2', '0.2s', '2.4s'], ['38%', '#f2b45e', '0.6s', '2.9s'], ['49%', '#ffffff', '0.3s', '2.7s'],
  ['60%', '#7fd6c2', '0.5s', '3.1s'], ['71%', '#f2b45e', '0.15s', '2.5s'], ['82%', '#7fd6c2', '0.8s', '3.2s'], ['92%', '#ffffff', '0.9s', '2.8s'],
]

/** Light paper falling once behind the welcome message. */
export function Confetti() {
  return (
    <>
      {CONFETTI.map(([left, colour, delay, length], i) => (
        <span key={left} aria-hidden className={cn('pointer-events-none absolute top-0 block', i % 2 ? 'h-2 w-2 rounded-full' : 'h-3.5 w-2.5')}
          style={{ left, background: colour, animation: `ci-confetti ${length} ease-in ${delay} both` }} />
      ))}
    </>
  )
}

/** The tick that draws itself inside a ring that ripples out, for a check in or out that worked. */
export function SuccessTick() {
  return (
    <div className="relative h-32 w-32">
      <span aria-hidden className="ci-burst absolute inset-0 rounded-full bg-white/35" />
      <span className="ci-pop absolute inset-0 flex items-center justify-center rounded-full bg-white">
        <svg width="68" height="68" viewBox="0 0 24 24" fill="none" stroke="#0f6b5c" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M5 12.5l4.5 4.5L19 7.5" style={{ strokeDasharray: 24, strokeDashoffset: 24, animation: 'ci-draw 0.6s ease 0.35s forwards' }} />
        </svg>
      </span>
    </div>
  )
}

export function Welcome({ time, place, late, onContinue }: { time: string; place: string | null; late: number; onContinue: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onContinue, 4000)
    return () => clearTimeout(timer)
  }, [onContinue])
  return (
    <Overlay label="You are checked in" tone="brand">
      <Confetti />
      <div className="mt-24 flex flex-col items-center text-center">
        <SuccessTick />
        <p className="ci-rise mt-8 text-3xl font-bold [animation-delay:0.4s]">You are checked in</p>
        <p className="ci-rise mt-2 text-lg text-white/90 [animation-delay:0.5s]">{time}{place ? ` at ${place}` : ''}</p>
        <span className="ci-rise mt-5 rounded-full bg-white/20 px-4 py-1.5 text-sm font-bold [animation-delay:0.6s]">{late > 0 ? `${late} min late` : 'On time'}</span>
      </div>
      <Button onClick={onContinue} className="ci-press mt-auto h-14 w-full rounded-2xl bg-white text-base font-bold text-brand-deep hover:bg-white/90">Continue</Button>
    </Overlay>
  )
}

export function Summary({ worked, inTime, outTime, openTasks, onDone }: { worked: string; inTime: string; outTime: string; openTasks: number; onDone: () => void }) {
  return (
    <Overlay label="Shift complete" tone="brand">
      <div className="mt-16 flex flex-col items-center text-center">
        <span className="ci-pop flex h-[72px] w-[72px] items-center justify-center rounded-full bg-white">
          <Check className="h-9 w-9 text-hero-a" strokeWidth={3} aria-hidden />
        </span>
        <p className="ci-rise mt-5 text-base text-white/90 [animation-delay:0.2s]">Shift complete. Thank you.</p>
        <p className="ci-rise mt-1 text-6xl font-bold tracking-tight [animation-delay:0.3s]">{worked}</p>
        <p className="ci-rise mt-1 text-sm text-white/85 [animation-delay:0.35s]">time on duty today</p>
      </div>
      <div className="ci-rise mt-8 w-full rounded-3xl bg-surface p-5 text-ink shadow-xl [animation-delay:0.4s]">
        <div className="flex items-center justify-between gap-3 text-center">
          <div className="flex-1"><p className="text-xs font-bold uppercase tracking-wider text-ink-muted">In</p><p className="mt-1 text-2xl font-bold tabular-nums">{inTime}</p></div>
          <span aria-hidden className="h-0.5 flex-1 rounded bg-gradient-to-r from-hero-a to-[#7fd6c2]" />
          <div className="flex-1"><p className="text-xs font-bold uppercase tracking-wider text-ink-muted">Out</p><p className="mt-1 text-2xl font-bold tabular-nums">{outTime}</p></div>
        </div>
        {openTasks > 0 && <p className="mt-4 rounded-xl bg-warn-soft px-3 py-2 text-sm font-semibold text-warn">Left with {openTasks} task(s) still open</p>}
      </div>
      <Button onClick={onDone} className="ci-press mt-auto h-14 w-full rounded-2xl bg-white text-base font-bold text-brand-deep hover:bg-white/90">Done</Button>
    </Overlay>
  )
}

export type ProblemKind = 'blocked' | 'unenrolled' | 'location'

const PROBLEMS: Record<ProblemKind, { icon: LucideIcon; label: string; title: string; text: string; tips: string[]; primary: string }> = {
  blocked: {
    icon: CameraOff, label: 'Camera blocked', title: 'We cannot use your camera',
    text: 'Check in needs the camera for the face check. The browser has it switched off for this app.',
    tips: ['Tap the lock or camera icon next to the address.', 'Set Camera to Allow.', 'Come back and try again.'], primary: 'Try again',
  },
  unenrolled: {
    icon: UserX, label: 'Not enrolled', title: 'Your face is not enrolled yet',
    text: 'The system has no photo of you to compare with, so the face check cannot run.',
    tips: ['Ask your manager to enroll your face. It takes a minute.', 'Once enrolled, come back and check in as usual.'], primary: 'Back to start',
  },
  location: {
    icon: MapPin, label: 'Location', title: 'We could not confirm where you are',
    text: 'Check in is only allowed at the outlet you are working at.',
    tips: ['Walk to the outlet and try again.', 'Switch on precise location for the browser.', 'Working somewhere else today? Pick that location first.'], primary: 'Check my location again',
  },
}

/** What went wrong, what to do about it, and one clear next step. */
export function Problem({ kind, detail, onRetry, onBack }: { kind: ProblemKind; detail?: string; onRetry: () => void; onBack: () => void }) {
  const p = PROBLEMS[kind]
  const Icon = p.icon
  return (
    <Overlay label={p.title} tone="light">
      <div className="-mx-6 -mt-14 flex w-[calc(100%+3rem)] flex-col items-center rounded-b-[36px] bg-gradient-to-br from-side to-hero-b px-7 pb-12 pt-14 text-white">
        <span className="ci-rise rounded-full bg-white/15 px-3.5 py-1 text-xs font-bold uppercase tracking-wide">{p.label}</span>
        <div className="ci-rise relative mt-7 h-48 w-48 [animation-delay:0.1s]">
          <svg width="192" height="192" viewBox="0 0 236 236" aria-hidden className="absolute inset-0"><circle cx="118" cy="118" r="112" fill="none" stroke="#f2b45e" strokeWidth="4" strokeDasharray="6 12" strokeLinecap="round" /></svg>
          <span className="absolute inset-3.5 flex items-center justify-center rounded-full bg-white/10"><Icon className="h-16 w-16 text-[#f2b45e]" strokeWidth={1.5} aria-hidden /></span>
        </div>
      </div>
      <div className="ci-rise -mt-8 w-full rounded-3xl bg-surface p-6 text-ink shadow-xl [animation-delay:0.2s]">
        <h2 className="text-xl font-bold leading-snug">{p.title}</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">{detail || p.text}</p>
        <ol className="mt-4 space-y-2.5">
          {p.tips.map((tip, i) => (
            <li key={tip} className="flex items-start gap-3 text-[15px] leading-snug">
              <span aria-hidden className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full bg-brand-soft text-[13px] font-bold text-brand-deep">{i + 1}</span>
              <span>{tip}</span>
            </li>
          ))}
        </ol>
      </div>
      <Button onClick={onRetry} className="ci-press ci-rise mt-5 h-14 w-full rounded-2xl text-base font-bold [animation-delay:0.3s]">{p.primary}</Button>
      {kind !== 'unenrolled' && <button type="button" onClick={onBack} className="ci-rise mt-2 min-h-12 px-4 text-[15px] font-bold text-brand-deep underline [animation-delay:0.36s]">Back to start</button>}
    </Overlay>
  )
}

/** A ring that fills as the shift goes on, with the running time inside. */
export function ProgressRing({ progress, children }: { progress: number; children: ReactNode }) {
  return (
    <div className="ci-rise relative mx-auto h-56 w-56 [animation-delay:0.1s]">
      <svg width="224" height="224" viewBox="0 0 224 224" aria-hidden>
        <circle cx="112" cy="112" r="84" fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="14" />
        <circle cx="112" cy="112" r="84" fill="none" stroke="#7fd6c2" strokeWidth="14" strokeLinecap="round" strokeDasharray="528" transform="rotate(-90 112 112)"
          style={{ strokeDashoffset: 528 * (1 - Math.min(1, Math.max(0, progress))), animation: 'ci-ring-in 1.2s cubic-bezier(0.2,0.8,0.2,1) 0.3s both' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  )
}
