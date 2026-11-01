import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/** The times a day a log is checked at: up to six, each different. */
export function TimesEditor({ times, onChange }: { times: string[]; onChange: (times: string[]) => void }) {
  return (
    <div className="space-y-2">
      {times.map((t, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input type="time" required aria-label={`Time ${i + 1}`} className="w-36" value={t} onChange={(e) => onChange(times.map((x, n) => (n === i ? e.target.value : x)))} />
          {times.length > 1 && <Button type="button" variant="ghost" size="icon" aria-label="Remove time" onClick={() => onChange(times.filter((_, n) => n !== i))}><X className="h-4 w-4" /></Button>}
        </div>
      ))}
      {times.length < 6 && <Button type="button" variant="outline" size="sm" onClick={() => onChange([...times, ''])}><Plus className="h-4 w-4" /> Add another time</Button>}
    </div>
  )
}

