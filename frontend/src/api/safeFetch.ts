import { isAllowedEndpoint } from '../contracts/allowed-endpoints'

export const DEFAULT_FETCH_TIMEOUT_MS = 8_000
const LOCAL_DEFAULT_ORIGIN = 'http://localhost:8000'

/** Validated API origin — pathname/query/hash must be empty on configured base URL. */
export function resolveApiOrigin(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (!raw) {
    return LOCAL_DEFAULT_ORIGIN
  }
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    throw new Error('Invalid VITE_API_BASE_URL')
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Invalid VITE_API_BASE_URL protocol')
  }
  if (url.username || url.password) {
    throw new Error('Credentials in VITE_API_BASE_URL are not allowed')
  }
  if (url.search || url.hash) {
    throw new Error('Query/hash in VITE_API_BASE_URL are not allowed')
  }
  if (url.pathname && url.pathname !== '/') {
    throw new Error('Path in VITE_API_BASE_URL is not allowed; set origin only')
  }
  return url.origin
}

export async function safeGetJson<T>(
  path: string,
  validate: (value: unknown) => value is T,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<T> {
  if (path.includes('?') || path.includes('#')) {
    throw new Error('Query/hash not allowed on API path')
  }
  if (!isAllowedEndpoint('GET', path)) {
    throw new Error(`Blocked endpoint: ${path}`)
  }
  const timeoutMs = options?.timeoutMs ?? DEFAULT_FETCH_TIMEOUT_MS
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const external = options?.signal
  const onExternalAbort = () => controller.abort()
  if (external) {
    if (external.aborted) {
      controller.abort()
    } else {
      external.addEventListener('abort', onExternalAbort, { once: true })
    }
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
    if (external) {
      external.removeEventListener('abort', onExternalAbort)
    }
  }
}