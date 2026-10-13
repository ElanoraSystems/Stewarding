import { CheckCircle2, CircleAlert, X } from 'lucide-react'
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

type Tone = 'ok' | 'error'
interface ToastItem {
  id: number
  tone: Tone
  text: string
  count: number
}

const ToastContext = createContext<((tone: Tone, text: string) => void) | null>(null)
const SHOWN = 3
const LIFETIME = 4000
let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id))
    timers.current.delete(id)
    setItems((current) => current.filter((t) => t.id !== id))
  }, [])

  // the same message again counts up on the toast already showing instead of stacking a copy
  const push = useCallback((tone: Tone, text: string) => {
    setItems((current) => {
      const same = current.find((t) => t.tone === tone && t.text === text)
      const id = same?.id ?? nextId++
      clearTimeout(timers.current.get(id))
      timers.current.set(id, setTimeout(() => dismiss(id), LIFETIME))
      const next = same ? current.map((t) => (t.id === id ? { ...t, count: t.count + 1 } : t)) : [...current, { id, tone, text, count: 1 }]
      return next.slice(-SHOWN)
    })
  }, [dismiss])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-[60] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={cn('toast-in flex items-start gap-3 rounded-lg border border-border border-l-4 bg-surface px-3 py-3 text-sm shadow-lg',
            t.tone === 'ok' ? 'border-l-ok' : 'border-l-danger')}>
            {t.tone === 'ok' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />}
            <p className="flex-1 text-ink">{t.text}{t.count > 1 && <span className="ml-2 rounded-full bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-ink-muted">x{t.count}</span>}</p>
            <button type="button" aria-label="Dismiss" className="text-ink-muted hover:text-ink" onClick={() => dismiss(t.id)}><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const push = useContext(ToastContext)
  if (!push) throw new Error('useToast must be used inside ToastProvider')
  return push
}

/** Runs an async action, toasts success or the API error message, and reports whether it worked. */
export function useRun() {
  const toast = useToast()
  return useCallback(
    async (action: () => Promise<unknown>, success?: string): Promise<boolean> => {
      try {
        await action()
        if (success) toast('ok', success)
        return true
      } catch (err) {
        toast('error', err instanceof ApiError || err instanceof Error ? err.message : 'Something went wrong')
        return false
      }
    },
    [toast],
  )
}
