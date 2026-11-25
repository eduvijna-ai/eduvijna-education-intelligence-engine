/** UI readiness states — default deny; never grants backend authority. */
export type ReadinessState =
  | 'unavailable'
  | 'blocked'
  | 'source_pending'
  | 'diagnostic_only'
  | 'connection_only'

export type FeatureKey =
  | 'shell'
  | 'health_probe'
  | 'question_studio'
  | 'student_runner'
  | 'student_results'
  | 'teacher_diagnostics'
  | 'student_diagnostics'
  | 'remediation_surface'
  | 'knowledge_library'
  | 'source_admin'
  | 'pack_onboarding'
  | 'policy_admin'
  | 'auth_design'
  | 'generation_jobs'
  | 'paper_export'

export type FeatureCapability = {
  readonly key: FeatureKey
  readonly label: string
  readonly readiness: ReadinessState
  readonly syntheticDemo: boolean
  readonly networkCallsAllowed: boolean
  readonly rationale: string
}

export type CapabilityMatrix = Readonly<Record<FeatureKey, FeatureCapability>>