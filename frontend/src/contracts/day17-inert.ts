/**
 * Non-operational typed contracts mirroring proposed Day17 shapes (PR61 held).
 * No runtime client invokes these URLs while Day17 remains unmerged.
 */

export type JobLifecycleState =
  | 'queued'
  | 'planning'
  | 'generating'
  | 'validating'
  | 'repairing'
  | 'completed'
  | 'failed'
  | 'canceled'

export type InertJobRecord = {
  readonly job_id: string
  readonly state: JobLifecycleState
  readonly capability: 'CONTRACT_ONLY'
}

export type InertAuthSessionContract = {
  readonly authenticated: false
  readonly session_present: false
  readonly day17_status: 'ON_HOLD'
}

export type InertMcpToolContract = {
  readonly tool_name: string
  readonly invokable: false
  readonly reason: 'DAY17_HELD'
}

export const INERT_JOB_CREATE_RESPONSE: InertJobRecord = {
  job_id: '',
  state: 'queued',
  capability: 'CONTRACT_ONLY',
}

export const INERT_AUTH_CONTRACT: InertAuthSessionContract = {
  authenticated: false,
  session_present: false,
  day17_status: 'ON_HOLD',
}