import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PaginationProps {
  page: number
  size: number
  total: number
  onPage: (page: number) => void
}

export function Pagination({ page, size, total, onPage }: PaginationProps) {
  if (total === 0) return null
  const from = (page - 1) * size + 1
  const to = Math.min(page * size, total)
  return (
    <div className="flex items-center justify-between gap-2 text-sm text-ink-muted">
      <span>
        {from}-{to} of {total}
      </span>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" aria-label="Next page" disabled={to >= total} onClick={() => onPage(page + 1)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
