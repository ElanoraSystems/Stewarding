import { Construction } from 'lucide-react'
import { Navigate, useParams } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'

const PHASE: Record<string, number> = {
  tasks: 5, reports: 5, audit: 5, settings: 5,
}

export function ModulePage() {
  const { key = '' } = useParams()
  const { me } = useAuth()
  const module = me?.modules.find((m) => m.key === key)
  if (!module) return <Navigate to="/" replace />

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{module.label}</h1>
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
          <Construction className="h-8 w-8 text-ink-muted" aria-hidden />
          <p className="font-medium">Not built yet</p>
          <p className="text-sm text-ink-muted">This module is planned for Phase {PHASE[key] ?? '?'}.</p>
        </CardContent>
      </Card>
    </div>
  )
}
