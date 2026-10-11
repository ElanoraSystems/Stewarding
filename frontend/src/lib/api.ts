const TOKEN_KEY = 'stw_token'

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

function messageOf(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg).filter(Boolean).join('; ') || 'Invalid input'
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message)
  return 'Request failed'
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const token = tokenStore.get()
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { ...(init.headers ?? {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check that the backend is running and that the dev proxy points at it (VITE_API_TARGET).')
  }
  if (!response.ok) {
    const detail = await response.json().then((d) => d.detail).catch(() => undefined)
    throw new ApiError(response.status, messageOf(detail), detail)
  }
  return response.json() as Promise<T>
}

export function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  return send<T>(path, {
    method: init.method ?? (init.body !== undefined ? 'POST' : 'GET'),
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  })
}

export async function uploadFile(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  const { name } = await send<{ name: string }>('/uploads', { method: 'POST', body: form })
  return name
}

export async function uploadLogo(file: File): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  await send('/organization/logo', { method: 'POST', body: form })
}
