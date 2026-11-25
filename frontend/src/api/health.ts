import { safeGetJson } from './safeFetch'

export type HealthProbe = {
  connected: boolean
  readiness: 'connection_only'
  featureReady: false
  endpoint: string
  detail: string
}

function isHealthPayload(value: unknown): value is { status: string } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    typeof (value as { status: unknown }).status === 'string'
  )
}

export async function probeHealth(signal?: AbortSignal): Promise<HealthProbe> {
  const path = '/health'
  try {
    const payload = await safeGetJson(path, isHealthPayload, { signal })
    const connected = payload.status.toLowerCase() === 'ok'
    return {
      connected,
      readiness: 'connection_only',
      featureReady: false,
      endpoint: path,
      detail: connected ? 'Health payload validated' : `Unexpected status: ${payload.status}`,
    }
  } catch (err) {
    return {
      connected: false,
      readiness: 'connection_only',
      featureReady: false,
      endpoint: path,
      detail: err instanceof Error ? err.message : 'Network error',
    }
  }
}