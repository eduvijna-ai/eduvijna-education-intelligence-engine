/** Only merged, verified backend routes the UI may call (D18-05, D18-32). */
export const ALLOWED_MERGED_ENDPOINTS = [
  { method: 'GET', path: '/health', purpose: 'Liveness probe' },
  { method: 'GET', path: '/ready', purpose: 'Readiness probe' },
  { method: 'GET', path: '/api/v1/system/info', purpose: 'System metadata' },
] as const

export type AllowedEndpoint = (typeof ALLOWED_MERGED_ENDPOINTS)[number]

export function isAllowedEndpoint(method: string, path: string): boolean {
  const normalized = path.split('?')[0] ?? path
  return ALLOWED_MERGED_ENDPOINTS.some(
    (e) => e.method === method.toUpperCase() && e.path === normalized,
  )
}