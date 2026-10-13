import { APP_NAME } from '@/lib/brand'

interface BrandMarkProps {
  organization: string
  hasLogo: boolean
  version?: number
  inverse?: boolean
}

/** The organization's logo and name above the product name; falls back to the product name alone. */
export function BrandMark({ organization, hasLogo, version = 0, inverse = false }: BrandMarkProps) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      {hasLogo && <img src={`/api/organization/logo?v=${version}`} alt="" className="h-9 w-auto max-w-24 rounded-md bg-white object-contain p-0.5" />}
      <div className="min-w-0 leading-tight">
        <p className="truncate font-semibold">{organization || APP_NAME}</p>
        {organization && <p className={inverse ? 'truncate text-xs text-white/60' : 'truncate text-xs text-ink-muted'}>{APP_NAME}</p>}
      </div>
    </div>
  )
}
