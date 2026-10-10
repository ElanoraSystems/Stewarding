import { cn } from '@/lib/utils'

interface KpiCardProps {
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'critical' | 'warn' | 'ok'
}

const TONES = {
  default: 'border-border bg-surface',
  critical: 'border-danger/50 bg-danger-soft',
  warn: 'border-warn/50 bg-warn-soft',
  ok: 'border-ok/40 bg-ok-soft',
}

export function KpiCard({ label, value, hint, tone = 'default' }: KpiCardProps) {
  return (
    <div className={cn('rounded-lg border p-4', TONES[tone])}>
      <p className="text-xs font-medium text-ink-muted">{label}</p>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', tone === 'critical' && 'text-danger')}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
    </div>
  )
}
