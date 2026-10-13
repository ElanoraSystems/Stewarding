import type { ReactNode } from 'react'

interface HeroCardProps {
  title: string
  subtitle?: string
  eyebrow?: string
  chips?: { label: string; urgent?: boolean }[]
  children?: ReactNode
}

/** The gradient greeting card at the top of a dashboard, with short facts as pills. */
export function HeroCard({ title, subtitle, eyebrow, chips = [], children }: HeroCardProps) {
  return (
    <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand to-brand-deep p-6 text-white shadow-[0_10px_30px_rgba(37,99,214,0.25)]">
      <div aria-hidden className="pointer-events-none absolute -right-10 -top-16 h-52 w-52 rounded-full bg-white/10" />
      <div aria-hidden className="pointer-events-none absolute -bottom-20 right-24 h-40 w-40 rounded-full bg-white/10" />
      <div className="relative space-y-1">
        {eyebrow && <p className="text-xs font-medium uppercase tracking-wide text-white/70">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold">{title}</h1>
        {subtitle && <p className="text-sm text-white/80">{subtitle}</p>}
      </div>
      {chips.length > 0 && (
        <ul className="relative mt-4 flex flex-wrap gap-2">
          {chips.map((c) => (
            <li key={c.label} className={c.urgent ? 'rounded-full bg-white px-3 py-1 text-xs font-semibold text-danger' : 'rounded-full bg-white/15 px-3 py-1 text-xs font-medium'}>{c.label}</li>
          ))}
        </ul>
      )}
      {children && <div className="relative mt-4">{children}</div>}
    </section>
  )
}

export function greeting(now = new Date()): string {
  const hour = now.getHours()
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}
