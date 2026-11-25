/** Only merged, verified backend routes the UI may call (D18-05, D18-32). */
export const ALLOWED_MERGED_ENDPOINTS = [
  { method: 'GET', path: '/health', purpose: 'Liveness probe' },
  { method: 'GET', path: '/ready', purpose: 'Readiness probe' },
  { method: 'GET', path: '/api/v1/system/info', purpose: 'System metadata' },
] as const

export type AllowedEndpoint = (typeof ALLOWED_MERGED_ENDPOINTS)[number]

const ALLOWED_PATH_SET = new Set(ALLOWED_MERGED_ENDPOINTS.map((e) => e.path))

export function isAllowedEndpoint(method: string, path: string): boolean {
  const normalized = path.split('?')[0]?.split('#')[0] ?? path
  if (method.toUpperCase() !== 'GET') return false
  return ALLOWED_PATH_SET.has(normalized as (typeof ALLOWED_MERGED_ENDPOINTS)[number]['path'])
}

export function assertExactAllowlist(pathsInSource: readonly string[]): boolean {
  if (pathsInSource.length !== ALLOWED_MERGED_ENDPOINTS.length) return false
  return pathsInSource.every((p) => ALLOWED_PATH_SET.has(p as never))
}