import type { CapabilityMatrix, FeatureCapability, FeatureKey, ReadinessState } from './types'

function cap(
  key: FeatureKey,
  label: string,
  readiness: ReadinessState,
  syntheticDemo: boolean,
  networkCallsAllowed: boolean,
  rationale: string,
): FeatureCapability {
  return Object.freeze({ key, label, readiness, syntheticDemo, networkCallsAllowed, rationale })
}

/** Fixed deny-by-default matrix — not derived from URL, storage, env, or mock flags. */
const FIXED_MATRIX_SOURCE: CapabilityMatrix = {
  shell: cap('shell', 'Product shell', 'diagnostic_only', true, false, 'Navigation layout only'),
  health_probe: cap(
    'health_probe',
    'Backend health probe',
    'connection_only',
    false,
    true,
    'Merged /health and /api/v1/system/info only',
  ),
  question_studio: cap(
    'question_studio',
    'Question & assessment studio',
    'diagnostic_only',
    true,
    false,
    'Day14 issuance/validation disabled; generation held',
  ),
  student_runner: cap(
    'student_runner',
    'Student runner',
    'diagnostic_only',
    true,
    false,
    'Non-actionable synthetic demo; no attempts',
  ),
  student_results: cap(
    'student_results',
    'Student results',
    'diagnostic_only',
    true,
    false,
    'Illustrative figures only',
  ),
  teacher_diagnostics: cap(
    'teacher_diagnostics',
    'Teacher diagnostics',
    'diagnostic_only',
    true,
    false,
    'Synthetic class fixtures; Day15 learner intel on hold',
  ),
  student_diagnostics: cap(
    'student_diagnostics',
    'Student diagnostics',
    'diagnostic_only',
    true,
    false,
    'Unknown vs weak distinction; no real ranking',
  ),
  remediation_surface: cap(
    'remediation_surface',
    'Adaptive remediation',
    'blocked',
    true,
    false,
    'Day16 runtime remediation disabled',
  ),
  knowledge_library: cap(
    'knowledge_library',
    'Knowledge library',
    'unavailable',
    false,
    false,
    'Day7 RAG operational boundary; no fake hits',
  ),
  source_admin: cap(
    'source_admin',
    'Source administration',
    'blocked',
    false,
    false,
    'Live source intake disabled Day12',
  ),
  pack_onboarding: cap(
    'pack_onboarding',
    'Exam/curriculum onboarding',
    'source_pending',
    false,
    false,
    'Official pack evidence pending',
  ),
  policy_admin: cap(
    'policy_admin',
    'Policy & API admin',
    'unavailable',
    false,
    false,
    'Day17 REST/auth/MCP on hold',
  ),
  auth_design: cap(
    'auth_design',
    'Authentication surfaces',
    'unavailable',
    false,
    false,
    'Day17 held; design contract only',
  ),
  generation_jobs: cap(
    'generation_jobs',
    'Async generation jobs',
    'blocked',
    true,
    false,
    'No job create/poll/cancel',
  ),
  paper_export: cap(
    'paper_export',
    'Print & JSON export',
    'diagnostic_only',
    true,
    false,
    'Watermarked synthetic export only',
  ),
}

Object.freeze(FIXED_MATRIX_SOURCE)

export type UntrustedElevationInput = {
  urlSearch?: string
  storageSnapshot?: Record<string, string>
  roleFixture?: string
  mockFlag?: boolean
  callerPrivilege?: string
}

function cloneMatrix(): CapabilityMatrix {
  const out = {} as Record<FeatureKey, FeatureCapability>
  for (const key of Object.keys(FIXED_MATRIX_SOURCE) as FeatureKey[]) {
    out[key] = Object.freeze({ ...FIXED_MATRIX_SOURCE[key] })
  }
  return Object.freeze(out) as CapabilityMatrix
}

/**
 * Resolve capabilities from fixed policy only. All caller-supplied elevation inputs are ignored.
 * Returns an isolated frozen snapshot per call.
 */
export function resolveCapabilities(_input?: UntrustedElevationInput): CapabilityMatrix {
  void _input
  return cloneMatrix()
}

export function featureReadyForDemo(key: FeatureKey): boolean {
  const state = FIXED_MATRIX_SOURCE[key].readiness
  return state === 'diagnostic_only' || state === 'connection_only'
}

export function assertActionBlocked(
  key: FeatureKey,
  action: string,
): { allowed: false; reason: string } {
  const feat = FIXED_MATRIX_SOURCE[key]
  return {
    allowed: false,
    reason: `${action} blocked: ${feat.label} is ${feat.readiness} (${feat.rationale})`,
  }
}