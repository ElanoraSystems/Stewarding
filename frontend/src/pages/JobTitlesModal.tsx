import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useLookup } from '@/lib/useLookups'

interface Props {
  point: { id: number; name: string; visible_to: string[] | null }
  onClose: () => void
  onSaved: () => void
  /** Where the choice is saved, and the words around it; the defaults are for a monitoring point. */
  path?: string
  title?: string
  description?: string
}

/** Chooses which job titles use a monitoring point or a checklist. Nothing ticked means everyone who can. Managers always can. */
export function JobTitlesModal({ point, onClose, onSaved, path = `/equipment/${point.id}`, title = `Who records ${point.name}`, description = 'Tick the job titles that see and record this log. Leave all unticked and everyone who can record monitoring sees it. Managers always see it.' }: Props) {
  const run = useRun()
  const titles = useLookup('job_title')
  const [chosen, setChosen] = useState<string[]>(point.visible_to ?? [])
  // the titles from Settings, plus any already chosen that were later retired, so they can still be unticked
  const options = [...titles, ...chosen.filter((t) => !titles.includes(t))]
  const toggle = (name: string) => setChosen((c) => (c.includes(name) ? c.filter((n) => n !== name) : [...c, name]))

  async function save() {
    if (await run(() => api(path, { method: 'PUT', body: { visible_to: chosen } }), 'Saved')) onSaved()
  }

  return (
    <Modal open title={title} onClose={onClose} size="sm"
      description={description}
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save}>Save</Button></>}>
      <fieldset className="space-y-2">
        <legend className="sr-only">Job titles</legend>
        {options.map((t) => (
          <label key={t} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={chosen.includes(t)} onChange={() => toggle(t)} /> {t}
          </label>
        ))}
        {options.length === 0 && <p className="text-sm text-ink-muted">No job titles are set up yet. Add them in Settings first.</p>}
      </fieldset>
    </Modal>
  )
}
