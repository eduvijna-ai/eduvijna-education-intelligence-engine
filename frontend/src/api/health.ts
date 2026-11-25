import { isAllowedEndpoint } from '../contracts/allowed-endpoints'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type HealthProbe = {
  connected: boolean
  featureReady: false
  endpoint: string
  detail: string
}

export async function probeHealth(signal?: AbortSignal): Promise<HealthProbe> {
  const path = '/health'
  if (!isAllowedEndpoint('GET', path)) {
    return {
      connected: false,
      featureReady: false,
      endpoint: path,
      detail: 'Endpoint blocked by client policy',
    }
  }
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { signal })
    return {
      connected: response.ok,
      featureReady: false,
      endpoint: path,
      detail: response.ok ? 'Backend reachable' : `HTTP ${response.status}`,
    }
  } catch (err) {
    return {
      connected: false,
      featureReady: false,
      endpoint: path,
      detail: err instanceof Error ? err.message : 'Network error',
    }
  }
}