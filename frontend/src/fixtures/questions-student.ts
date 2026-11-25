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
    stem:
      'Select all base quantities used in kinematics (synthetic demo). Multiple answers may apply; no scoring.',
    type: 'multiselect',
    options: ['Length', 'Mass', 'Temperature', 'Time'],
    maxMarks: 2,
  },
  {
    id: 's-q-friction-03',
    stem: 'Enter the numeric magnitude of acceleration in SI units (number only, e.g. 9.8).',
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
