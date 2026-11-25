import type { SystemInfo } from '../types/system'

import { safeGetJson } from './safeFetch'

function isSystemInfo(value: unknown): value is SystemInfo {
  if (typeof value !== 'object' || value === null) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.service === 'string' &&
    typeof row.status === 'string' &&
    typeof row.environment === 'string' &&
    typeof row.api_version === 'string'
  )
}

export async function getSystemInfo(signal?: AbortSignal): Promise<SystemInfo> {
  return safeGetJson('/api/v1/system/info', isSystemInfo, { signal })
}