const TOKEN_KEY = 'stw_token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = tokenStore.get()
  const response = await fetch(`/api${path}`, {
    method: init.method ?? (init.body ? 'POST' : 'GET'),
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: init.body ? JSON.stringify(init.body) : undefined,
  })
  if (!response.ok) {
    const detail = await response.json().then((d) => d.detail).catch(() => undefined)
    throw new ApiError(response.status, typeof detail === 'string' ? detail : 'Request failed')
  }
  return response.json() as Promise<T>
}
