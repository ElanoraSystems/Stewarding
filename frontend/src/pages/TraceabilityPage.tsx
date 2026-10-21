import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { FoodItemsTab } from '@/pages/trace/FoodItemsTab'
import { LotsTab } from '@/pages/trace/LotsTab'
import { ReceiveLotForm } from '@/pages/trace/ReceiveLotForm'
import { RulesTab } from '@/pages/trace/RulesTab'
import { SplitLotForm } from '@/pages/trace/SplitLotForm'

const TABS = [
  ['lots', 'Lots', 'lot.view'],
  ['receive', 'Receive food', 'lot.receive'],
  ['split', 'Split a lot', 'lot.split'],
  ['rules', 'Shelf life', 'lot.view'],
  ['items', 'Food items', 'lot.manage'],
] as const

type Tab = (typeof TABS)[number][0]

export function TraceabilityPage() {
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const [version, setVersion] = useState(0)
  const allowed = TABS.filter(([, , permission]) => me?.permissions.includes(permission))
  const requested = params.get('tab')
  const tab: Tab = (allowed.find(([key]) => key === requested) ?? allowed[0])?.[0] ?? 'lots'
  const refresh = () => setVersion((v) => v + 1)

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Food Traceability</h1>
        <p className="text-sm text-ink-muted">Receive food into lots, split them into labelled portions, and follow any lot from the supplier to the cooking record.</p>
      </div>
      <div role="tablist" aria-label="Traceability sections" className="flex gap-2 overflow-x-auto pb-1">
        {allowed.map(([key, text]) => (
          <Button key={key} role="tab" aria-selected={tab === key} size="sm" variant={tab === key ? 'default' : 'outline'} className="shrink-0" onClick={() => setParams({ tab: key })}>{text}</Button>
        ))}
      </div>
      {tab === 'lots' && <LotsTab key={version} />}
      {tab === 'receive' && <ReceiveLotForm onSaved={refresh} />}
      {tab === 'split' && <SplitLotForm onSaved={refresh} />}
      {tab === 'rules' && <RulesTab />}
      {tab === 'items' && <FoodItemsTab />}
    </div>
  )
}
