import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Skeleton } from '@/components/ui/table'
import { fmtDateTime } from '@/lib/format'
import { useApi } from '@/lib/useApi'

interface Row { when: string; by: string; what: string; subject: string; changes: { field: string; from: string | null; to: string | null }[] }

/** Who changed a checklist or a monitoring point, when, and from what to what. Read only: it is taken from the audit log. */
export function ChangeHistoryModal({ title, path, onClose }: { title: string; path: string; onClose: () => void }) {
  const { data, error } = useApi<Row[]>(path)
  return (
    <Modal open title={title} description="Newest first. The records already made keep the wording and limits they were made under." size="lg" onClose={onClose} footer={<Button variant="outline" onClick={onClose}>Close</Button>}>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {!data && !error && <Skeleton className="h-24 w-full" />}
      {data && data.length === 0 && <p className="text-sm text-ink-muted">No changes recorded.</p>}
      {data && data.length > 0 && (
        <ol className="space-y-3 text-sm">
          {data.map((r, i) => (
            <li key={i} className="rounded-lg border border-border bg-surface p-3">
              <p className="font-medium">{r.what}{r.subject && <span className="font-normal">: {r.subject}</span>}</p>
              <p className="text-xs text-ink-muted">{fmtDateTime(r.when)} by {r.by}</p>
              {r.changes.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {r.changes.map((c) => (
                    <li key={c.field}><span className="text-ink-muted">{c.field}:</span> {c.from === null ? <span>{c.to}</span> : c.to === null ? <span className="line-through">{c.from}</span> : <span>{c.from} <span aria-hidden>&rarr;</span><span className="sr-only">changed to</span> {c.to}</span>}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </Modal>
  )
}
