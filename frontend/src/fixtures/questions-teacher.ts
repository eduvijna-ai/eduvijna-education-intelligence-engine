/** Teacher preview metadata — answer keys omitted from client bundle (D18-13, F18-02). */
export type TeacherQuestionFixture = {
  id: string
  stem: string
  type: 'mcq' | 'multiselect' | 'numerical' | 'descriptive'
  difficulty: 'foundation' | 'moderate' | 'stretch'
  bloom: string
  competency: string
  learningOutcome: string
  prerequisite: string
  rubric: string
  options?: string[]
  /** Design placeholder only — no correctness payload shipped. */
  answerMetadataStatus: 'unavailable_in_client_bundle'
  provenanceRevision: 'unavailable'
  provenanceLocator: 'unavailable'
  evidenceStatus: 'synthetic_fixture'
}

export const BLOOM_LEVELS = [
  'Remember',
  'Understand',
  'Apply',
  'Analyze',
  'Evaluate',
] as const

export const SYNTHETIC_COMPETENCY_CODES = [
  'SYN-C1-conceptual-recall',
  'SYN-C2-procedure-apply',
  'SYN-C3-model-interpret',
  'SYN-C4-error-diagnose',
  'SYN-C5-represent-explain',
  'SYN-C6-transfer-synthetic',
] as const

export const TEACHER_QUESTION_FIXTURES: TeacherQuestionFixture[] = [
  {
    id: 't-q-kinematics-01',
    stem: 'For motion along a straight line, average velocity is:',
    type: 'mcq',
    difficulty: 'foundation',
    bloom: 'Understand',
    competency: 'SYN-C1-conceptual-recall',
    learningOutcome: 'Relate displacement and time for uniform intervals.',
    prerequisite: 'Linear motion definitions',
    rubric: 'Select the definition matching total displacement over total time.',
    options: [
      'Total path length divided by time',
      'Total displacement divided by time',
      'Instantaneous speed at midpoint',
      'Change in acceleration over time',
    ],
    answerMetadataStatus: 'unavailable_in_client_bundle',
    provenanceRevision: 'unavailable',
    provenanceLocator: 'unavailable',
    evidenceStatus: 'synthetic_fixture',
  },
  {
    id: 't-q-kinematics-02',
    stem: 'If $s = 2t^2$ (SI units), magnitude of velocity at $t=3$ s is:',
    type: 'numerical',
    difficulty: 'moderate',
    bloom: 'Apply',
    competency: 'SYN-C2-procedure-apply',
    learningOutcome: 'Differentiate position to obtain velocity.',
    prerequisite: 'Power rule for derivatives',
    rubric: 'Numeric response validated only when generation is enabled (held).',
    answerMetadataStatus: 'unavailable_in_client_bundle',
    provenanceRevision: 'unavailable',
    provenanceLocator: 'unavailable',
    evidenceStatus: 'synthetic_fixture',
  },
]