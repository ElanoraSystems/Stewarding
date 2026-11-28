import { describe, expect, it } from 'vitest'
import { REPORTS, SECTIONS } from '@/lib/reportCatalog'

describe('report catalog', () => {
  it('tells each checklist report apart: a name and a sentence on what it shows', () => {
    const checklist = REPORTS.filter((r) => r.section === 'Checklists')
    expect(checklist.map((r) => r.title)).toEqual(['Checklist sign-off sheet', 'Checklist record'])
    for (const r of [...checklist, REPORTS.find((x) => x.key === 'approvals')!]) expect(r.about && r.about.length > 40).toBe(true)
  })

  it('keeps approval decisions with the overview, since they cover monitoring readings and alerts as well as checklists', () => {
    expect(REPORTS.find((r) => r.key === 'approvals')).toMatchObject({ title: 'Approval decisions', section: 'Overview' })
    expect(SECTIONS).toContain('Overview')
  })

  it('has no two reports with the same name', () => {
    const titles = REPORTS.map((r) => r.title)
    expect(new Set(titles).size).toBe(titles.length)
  })
})
