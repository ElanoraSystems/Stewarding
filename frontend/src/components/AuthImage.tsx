import { useEffect, useState } from 'react'
import { tokenStore } from '@/lib/api'

/** An uploaded image, fetched with the sign-in token because uploads are not public. Click to open it full size. */
export function AuthImage({ name, alt, className }: { name: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let revoked = false
    let made: string | null = null
    fetch(`/api/uploads/${name}`, { headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error('missing'))))
      .then((blob) => {
        if (revoked) return
        made = URL.createObjectURL(blob)
        setUrl(made)
      })
      .catch(() => setUrl(null))
    return () => {
      revoked = true
      if (made) URL.revokeObjectURL(made)
    }
  }, [name])

  if (!url) return <span className="text-xs text-ink-muted">{alt}</span>
  return (
    <a href={url} target="_blank" rel="noreferrer">
      <img src={url} alt={alt} className={className ?? 'h-10 w-auto rounded border border-border bg-white object-contain'} />
    </a>
  )
}
