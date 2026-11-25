/** Teacher preview metadata — answer keys omitted from client bundle (D18-13, F18-02). */
export type TeacherStemTable = {
  caption: string
  headers: string[]
  rows: string[][]
}

export type TeacherQuestionFixture = {
  id: string
  stem: string
  stemTable?: TeacherStemTable
  type: 'mcq' | 'multiselect' | 'numerical' | 'descriptive'
  difficulty: 'foundation' | 'moderate' | 'stretch'
  bloom: string
  competency: string
  competencyMappingStatus: 'synthetic_not_official_ariv'
  learningOutcome: string
  prerequisite: string
  rubric: string
  options?: string[]
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

export const ARIV_COMPETENCY_LABELS = [
  'Knowledge',
  'Conceptual Understanding',
  'Application',
  'Analysis',
  'Problem Solving',
  'HOTS',
] as const

export const TEACHER_QUESTION_FIXTURES: TeacherQuestionFixture[] = [
  {
    id: 't-q-kinematics-01',
    stem: 'For motion along a straight line, average velocity is:',
    type: 'mcq',
    difficulty: 'foundation',
    bloom: 'Understand',
    competency: 'Conceptual Understanding',
    competencyMappingStatus: 'synthetic_not_official_ariv',
    learningOutcome: 'Relate displacement and time for uniform intervals.',
    prerequisite: 'Linear motion definitions',
    rubric: 'Demonstrate conceptual understanding of average velocity (synthetic rubric contract).',
    options: [
      'Ratio involving total path length and elapsed time',
      'Ratio involving displacement and elapsed time',
      'Speed at the midpoint of the interval',
      'Change in acceleration over the interval',
    ],
    answerMetadataStatus: 'unavailable_in_client_bundle',
    provenanceRevision: 'unavailable',
    provenanceLocator: 'unavailable',
    evidenceStatus: 'synthetic_fixture',
  },
  {
    id: 't-q-stem-table-01',
    stem: 'Refer to the kinematics quantities table (synthetic layout fixture).',
    type: 'mcq',
    difficulty: 'foundation',
    bloom: 'Remember',
    competency: 'Knowledge',
    competencyMappingStatus: 'synthetic_not_official_ariv',
    learningOutcome: 'Identify base quantities in motion contexts.',
    prerequisite: 'SI units overview',
    rubric: 'Use the tabular reference for conceptual recall (synthetic contract).',
    options: [
      'Displacement is a scalar',
      'Time is a base quantity in this demo table',
      'Velocity is always negative',
      'Distance cannot be measured',
    ],
    answerMetadataStatus: 'unavailable_in_client_bundle',
    provenanceRevision: 'unavailable',
    provenanceLocator: 'unavailable',
    evidenceStatus: 'synthetic_fixture',
    stemTable: {
      caption: 'Synthetic kinematics reference (not official syllabus)',
      headers: ['Quantity', 'Symbol (demo)', 'SI unit'],
      rows: [
        ['Displacement', 's', 'm'],
        ['Time', 't', 's'],
        ['Velocity', 'v', 'm s⁻¹'],
      ],
    },
  },
  {
    id: 't-q-kinematics-02',
    stem: 'If $s = 2t^2$ (SI units), magnitude of velocity at $t=3$ s is:',
    type: 'numerical',
    difficulty: 'moderate',
    bloom: 'Apply',
    competency: 'Application',
    competencyMappingStatus: 'synthetic_not_official_ariv',
    learningOutcome: 'Differentiate position to obtain velocity.',
    prerequisite: 'Power rule for derivatives',
    rubric: 'Show derivative-based reasoning for velocity magnitude (synthetic contract; scoring held).',
    answerMetadataStatus: 'unavailable_in_client_bundle',
    provenanceRevision: 'unavailable',
    provenanceLocator: 'unavailable',
    evidenceStatus: 'synthetic_fixture',
  },
]