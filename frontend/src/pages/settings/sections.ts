export const SECTION_GROUPS = [
  { title: 'Company', items: [['organization', 'Organization'], ['locations', 'Locations'], ['shifts', 'Shifts']] },
  { title: 'People', items: [['roles', 'Roles']] },
  { title: 'Rules', items: [['general', 'Rules & alerts']] },
  { title: 'Food safety', items: [['monitoring', 'Monitoring setup']] },
  { title: 'Stock', items: [['items', 'Item master'], ['inventory', 'Categories & units'], ['suppliers', 'Suppliers']] },
  { title: 'Lists', items: [['lists', 'Dropdown lists']] },
] as const

export type SectionKey = (typeof SECTION_GROUPS)[number]['items'][number][0]

export const FIRST_SECTION: SectionKey = 'organization'

export const isSection = (key: string | null | undefined): key is SectionKey =>
  SECTION_GROUPS.some((group) => group.items.some(([sectionKey]) => sectionKey === key))
