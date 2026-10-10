import type { ReactNode } from 'react'

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1 text-sm font-medium">
      {label}
      {children}
      {hint && <span className="block text-xs font-normal text-ink-muted">{hint}</span>}
    </label>
  )
}
