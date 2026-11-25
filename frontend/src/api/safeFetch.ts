import { isAllowedEndpoint } from '../contracts/allowed-endpoints'

export const DEFAULT_FETCH_TIMEOUT_MS = 8_000

/** Validated API origin — rejects path/query injection via env. */
export function resolveApiOrigin(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  try {
    const url = new URL(raw)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      throw new Error('invalid protocol')
    }
    return url.origin
  } catch {
    return 'http://localhost:8000'
  }
}

export async function safeGetJson<T>(
  path: string,
  validate: (value: unknown) => value is T,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<T> {
  if (!isAllowedEndpoint('GET', path)) {
    throw new Error(`Blocked endpoint: ${path}`)
  }
  const timeoutMs = options?.timeoutMs ?? DEFAULT_FETCH_TIMEOUT_MS
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const signal = options?.signal
  if (signal) {
    signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  try {
    const response = await fetch(`${resolveApiOrigin()}${path}`, {
      method: 'GET',
      signal: controller.signal,
      credentials: 'omit',
      redirect: 'error',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`)
    }
    const body: unknown = await response.json()
    if (!validate(body)) {
      throw new Error('Unexpected response shape')
    }
    return body
  } finally {
    window.clearTimeout(timer)
  }
}