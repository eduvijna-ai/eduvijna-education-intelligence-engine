import type { SystemInfo } from '../types/system'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getSystemInfo(signal?: AbortSignal): Promise<SystemInfo> {
  const response = await fetch(`${API_BASE_URL}/api/v1/system/info`, { signal })
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`)
  }
  return response.json() as Promise<SystemInfo>
}
