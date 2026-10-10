import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

type Tone = 'ok' | 'error'
interface ToastItem {
  id: number
  tone: Tone
  text: string
}

const ToastContext = createContext<((tone: Tone, text: string) => void) | null>(null)
let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const push = useCallback((tone: Tone, text: string) => {
    const id = nextId++
    setItems((current) => [...current, { id, tone, text }])
    setTimeout(() => setItems((current) => current.filter((t) => t.id !== id)), 5000)
  }, [])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-[60] flex max-w-sm flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              'rounded-md px-4 py-3 text-sm shadow-lg',
              t.tone === 'ok' ? 'bg-ok text-white' : 'bg-danger text-white',
            )}
          >
            {t.text}
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
