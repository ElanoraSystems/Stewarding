import { MapPin } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'

const HEADINGS = {
  manager: { title: 'All locations', hint: 'Consolidated multi-location view.' },
  supervisor: { title: 'My locations', hint: 'Operations for your assigned locations.' },
  steward: { title: 'My shift today', hint: 'Your assigned location and tasks.' },
}

export function DashboardPage() {
  const { me } = useAuth()
  if (!me) return null
  const { title, hint } = HEADINGS[me.role]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-sm text-ink-muted">{hint}</p>
      </div>
      {me.locations.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-ink-muted">
            No location is assigned to your account. Ask a manager to assign one.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {me.locations.map((location) => (
            <Card key={location.id}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-brand" aria-hidden />
                  {location.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-ink-muted">
                {location.code} - {location.timezone}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
