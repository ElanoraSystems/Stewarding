import { useApi } from '@/lib/useApi'

export interface Item {
  id: number
  code: string
  name: string
  category_id: number
  unit_id: number
  category: string
  unit: string
  description: string | null
  image_path: string | null
  storage_location: string | null
  min_level: number
  target_level: number | null
  supplier_id: number | null
  supplier: string | null
  is_tracked_asset: boolean
  active: boolean
  qty: number
  received: number
  received_by_location: Record<string, number>
  by_location: Record<string, number>
  low: boolean
  short_at: { location_id: number; qty: number; minimum: number }[]
  location_minimums: Record<string, number>
  minimum: number
  unit_cost?: number | null
  value?: number | null
}

/** Every active item, for pickers and name lookups. */
export function useAllItems(): { items: Item[]; byId: Map<number, Item> } {
  const all = useApi<{ items: Item[] }>('/inventory/items?size=200')
  const items = all.data?.items ?? []
  return { items, byId: new Map(items.map((i) => [i.id, i])) }
}
