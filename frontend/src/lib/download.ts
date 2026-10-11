import { tokenStore } from '@/lib/api'

/** Fetches an authenticated file and saves it; returns false when the server refuses. */
export async function downloadFile(path: string, fallbackName: string): Promise<boolean> {
  const response = await fetch(path, { headers: { Authorization: `Bearer ${tokenStore.get()}` } })
  if (!response.ok) return false
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = response.headers.get('content-disposition')?.match(/filename="(.+)"/)?.[1] ?? fallbackName
  link.click()
  URL.revokeObjectURL(url)
  return true
}
