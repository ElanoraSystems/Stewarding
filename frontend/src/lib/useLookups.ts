import { useApi } from '@/lib/useApi'

export type LookupKind = 'job_title' | 'checklist_category' | 'breakage_reason' | 'corrective_action'

/** Active values of one managed list, for dropdowns and suggestions. */
export function useLookup(kind: LookupKind): string[] {
  const { data } = useApi<{ value: string }[]>(`/lookups?kind=${kind}`)
  return (data ?? []).map((v) => v.value)
}
