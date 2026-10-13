import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface KpiCardProps {
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'critical' | 'warn' | 'ok'
  icon?: LucideIcon
}

const TONES = {
  default: 'border-border bg-surface',
  critical: 'border-danger/50 bg-danger-soft',
  warn: 'border-warn/50 bg-warn-soft',
  ok: 'border-ok/40 bg-ok-soft',
}

const ICON_TONES = {
  default: 'bg-brand-soft text-brand',
  critical: 'bg-danger/10 text-danger',
  warn: 'bg-warn/10 text-warn',
  ok: 'bg-ok/10 text-ok',
}

export function KpiCard({ label, value, hint, tone = 'default', icon: Icon }: KpiCardProps) {
  return (
    <div className={cn('rounded-xl border p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]', TONES[tone])}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-ink-muted">{label}</p>
        {Icon && <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-lg', ICON_TONES[tone])}><Icon className="h-4 w-4" aria-hidden /></span>}
      </div>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', tone === 'critical' && 'text-danger')}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
    </div>
  )
}
