/** Student-safe runner items — no answer keys or correctness labels (D18-21..23). */
export type StudentQuestionFixture = {
  id: string
  stem: string
  type: 'mcq' | 'multiselect' | 'numerical' | 'descriptive'
  options?: string[]
  maxMarks: number
}

export const STUDENT_RUNNER_FIXTURES: StudentQuestionFixture[] = [
  {
    id: 's-q-friction-01',
    stem: 'Which quantity is a vector?',
    type: 'mcq',
    options: ['Speed', 'Distance', 'Displacement', 'Time'],
    maxMarks: 1,
  },
  {
    id: 's-q-friction-02',
    stem: 'Select all SI base quantities used in kinematics (demo).',
    type: 'multiselect',
    options: ['Length', 'Mass', 'Temperature', 'Time'],
    maxMarks: 2,
  },
  {
    id: 's-q-friction-03',
    stem: 'Enter the SI unit of acceleration.',
    type: 'numerical',
    maxMarks: 1,
  },
  {
    id: 's-q-friction-04',
    stem: 'Explain in one sentence when distance equals displacement.',
    type: 'descriptive',
    maxMarks: 2,
  },
]

/** Static assertion for verifier/tests — student bundle must stay key-free. */
export const STUDENT_FORBIDDEN_KEYS = [
  'correctAnswer',
  'answerKey',
  'explanation',
  'isCorrect',
] as const

export function studentFixtureIntegrityOk(items: unknown[]): boolean {
  for (const item of items) {
    if (typeof item !== 'object' || item === null) return false
    for (const key of STUDENT_FORBIDDEN_KEYS) {
      if (key in item) return false
    }
  }
  return true
}