import { useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton, Table, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useRun } from '@/lib/toast'
import { useApi } from '@/lib/useApi'
import type { Rules } from '@/pages/trace/types'

interface FoodItem {
  id: number
  name: string
  food_group: string
  group_label: string
  active: boolean
}

/** The foods that can be received, each in a group that decides its shelf life. */
export function FoodItemsTab() {
  const run = useRun()
  const items = useApi<FoodItem[]>('/lots/food-items?include_inactive=true')
  const rules = useApi<Rules>('/lots/rules')
  const [name, setName] = useState('')
  const [group, setGroup] = useState('poultry')

  async function add(event: FormEvent) {
    event.preventDefault()
    if (await run(() => api('/lots/food-items', { body: { name, food_group: group } }), 'Food item added')) {
      setName('')
      items.reload()
    }
  }

  async function toggle(item: FoodItem) {
    if (await run(() => api(`/lots/food-items/${item.id}`, { method: 'PUT', body: { active: !item.active } }), item.active ? 'Food item hidden' : 'Food item restored')) items.reload()
  }

  if (!items.data || !rules.data) return <Skeleton className="h-48 w-full" />
  return (
    <div className="space-y-4">
      <form onSubmit={add} className="flex flex-wrap items-end gap-3">
        <Field label="Food item"><Input required minLength={2} maxLength={120} className="w-64" placeholder="Chicken breast, skinless" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Group">
          <Select className="w-44" value={group} onChange={(e) => setGroup(e.target.value)}>
            {rules.data.groups.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
          </Select>
        </Field>
        <Button type="submit">Add food item</Button>
      </form>
      <Table>
        <thead><tr><Th>Food item</Th><Th>Group</Th><Th>Status</Th><Th /></tr></thead>
        <tbody>
          {items.data.map((i) => (
            <tr key={i.id}>
              <Td className="font-medium">{i.name}</Td>
              <Td>{i.group_label}</Td>
              <Td><Badge tone={i.active ? 'ok' : 'neutral'}>{i.active ? 'In use' : 'Hidden'}</Badge></Td>
              <Td className="text-right"><Button size="sm" variant="outline" onClick={() => toggle(i)}>{i.active ? 'Hide' : 'Restore'}</Button></Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
