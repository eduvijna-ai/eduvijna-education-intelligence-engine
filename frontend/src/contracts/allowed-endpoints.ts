/** Only merged, verified backend routes the UI may call (D18-05, D18-32). */
export const ALLOWED_MERGED_ENDPOINTS = [
  { method: 'GET', path: '/health', purpose: 'Liveness probe' },
  { method: 'GET', path: '/ready', purpose: 'Readiness probe' },
  { method: 'GET', path: '/api/v1/system/info', purpose: 'System metadata' },
] as const

export type AllowedEndpoint = (typeof ALLOWED_MERGED_ENDPOINTS)[number]

const ALLOWED_PAIRS = new Set(
  ALLOWED_MERGED_ENDPOINTS.map((e) => `${e.method}:${e.path}`),
)

export function isAllowedEndpoint(method: string, path: string): boolean {
  if (path.includes('?') || path.includes('#')) return false
  if (method.toUpperCase() !== 'GET') return false
  return ALLOWED_PAIRS.has(`GET:${path}`)
}