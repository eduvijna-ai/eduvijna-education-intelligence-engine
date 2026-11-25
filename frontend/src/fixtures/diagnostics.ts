export const SYNTHETIC_STUDENT_RESULT = {
  label: 'Illustrative score (synthetic)',
  scorePercent: 62,
  narrative:
    'Figures below are fixed demo samples. They do not reflect a real learner attempt.',
  unknownVsWeak: [
    { topic: 'Vector resolution', status: 'unknown', note: 'Insufficient evidence in demo.' },
    { topic: 'Kinematics graphs', status: 'weak_hypothesis', note: 'Demo hypothesis only — not verified.' },
  ],
}

export const SYNTHETIC_TEACHER_DIAGNOSTICS = {
  classLabel: 'Synthetic class cohort (no real names)',
  patterns: [
    { pattern: 'Sign errors in vector components', evidence: 'uncertain', share: '28% (demo)' },
    { pattern: 'Unit conversion slips', evidence: 'illustrative', share: '19% (demo)' },
  ],
}

export const SYNTHETIC_REMEDIATION_STAGES = [
  {
    stage: 'foundation',
    description: 'Conceptual revisit using internal synthetic items only.',
    actionable: false,
  },
  {
    stage: 'application',
    description: 'Guided practice illustrations — no scheduling or persistence.',
    actionable: false,
  },
  {
    stage: 'target_retest',
    description: 'Fresh retest items shown as placeholders; no issuance.',
    actionable: false,
  },
]