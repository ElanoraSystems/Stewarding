import { Inbox } from 'lucide-react'
import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded bg-surface-muted', className)} />
}

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface">
      <table className={cn('w-full text-left text-sm', className)} {...props} />
    </div>
  )
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn('border-b border-border bg-surface-muted px-4 py-2 font-medium text-ink-muted', className)} {...props} />
}

export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('border-b border-border px-4 py-3 align-middle', className)} {...props} />
}

export function SkeletonRows({ cols, rows = 5 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }, (_, c) => (
            <Td key={c}>
              <Skeleton className="h-4 w-full" />
            </Td>
          ))}
        </tr>
      ))}
    </>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <Inbox className="h-8 w-8 text-ink-muted" aria-hidden />
      <p className="font-medium">{title}</p>
      {hint && <p className="text-sm text-ink-muted">{hint}</p>}
      {action}
    </div>
  )
}
