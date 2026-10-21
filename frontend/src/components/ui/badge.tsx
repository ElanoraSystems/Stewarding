import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', {
  variants: {
    tone: {
      neutral: 'bg-surface-muted text-ink-muted ring-1 ring-inset ring-border',
      ok: 'bg-ok-soft text-ok ring-1 ring-inset ring-ok/20',
      warn: 'bg-warn-soft text-warn ring-1 ring-inset ring-warn/25',
      critical: 'bg-danger-soft text-danger font-semibold ring-1 ring-inset ring-danger/25',
    },
  },
  defaultVariants: { tone: 'neutral' },
})

export function Badge({ className, tone, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}
