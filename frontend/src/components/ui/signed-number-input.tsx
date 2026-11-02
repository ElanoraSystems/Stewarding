import type { InputHTMLAttributes } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/** What may be typed: an optional minus, digits and one decimal point. A comma becomes a point; a typographic minus becomes a plain one. */
export function cleanSigned(raw: string): string {
  const text = raw.replace(/[−–—]/g, '-').replace(',', '.')
  const negative = text.trimStart().startsWith('-')
  const [whole, ...rest] = text.replace(/[^0-9.]/g, '').split('.')
  return `${negative ? '-' : ''}${whole}${rest.length ? `.${rest.join('')}` : ''}`
}

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> {
  value: string
  onChange: (value: string) => void
}

/**
 * A number field that can be made negative on a phone: the iPhone number keypad has no minus key, so a +/- button sits beside the field
 * (typing a minus still works on a keyboard). The value stays text, so a partly typed "-" is allowed until the form is sent.
 */
export function SignedNumberInput({ value, onChange, className, ...props }: Props) {
  const negative = value.startsWith('-')
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Input {...props} type="text" inputMode="decimal" autoComplete="off" pattern="-?([0-9]+\.?[0-9]*|\.[0-9]+)" title="A number, such as 4 or -18.5"
        value={value} onChange={(e) => onChange(cleanSigned(e.target.value))} />
      <button type="button" aria-label={negative ? 'Make positive' : 'Make negative'} aria-pressed={negative} onClick={() => onChange(negative ? value.slice(1) : `-${value}`)}
        className={cn('h-10 w-12 shrink-0 rounded-lg border text-lg font-semibold pointer-coarse:h-11', negative ? 'border-brand bg-brand text-white' : 'border-border-strong bg-surface text-ink')}>
        {negative ? '−' : '+'}
      </button>
    </div>
  )
}
