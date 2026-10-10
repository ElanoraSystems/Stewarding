import { useApi } from '@/lib/useApi'

export interface Item {
  id: number
  kind: 'crockery' | 'smallware'
  code: string
  name: string
  category_id: number
  unit_id: number
  category: string
  unit: string
  description: string | null
  storage_location: string | null
  min_level: number
  target_level: number | null
  supplier: string | null
  is_tracked_asset: boolean
  active: boolean
  qty: number
  by_location: Record<string, number>
  low: boolean
  unit_cost?: number | null
  value?: number | null
}

/** Every active item of both kinds, for pickers and name lookups. */
export function useAllItems(): { items: Item[]; byId: Map<number, Item> } {
  const crockery = useApi<{ items: Item[] }>('/inventory/items?kind=crockery&size=200')
  const smallware = useApi<{ items: Item[] }>('/inventory/items?kind=smallware&size=200')
  const items = [...(crockery.data?.items ?? []), ...(smallware.data?.items ?? [])]
  return { items, byId: new Map(items.map((i) => [i.id, i])) }
}
