/** Teacher-only illustrative items with answer metadata (D18-13, D18-32). */
export type TeacherQuestionFixture = {
  id: string
  stem: string
  type: 'mcq' | 'numerical' | 'descriptive'
  difficulty: 'foundation' | 'moderate' | 'stretch'
  bloom: string
  competency: string
  learningOutcome: string
  prerequisite: string
  rubric: string
  options?: string[]
  correctAnswer: string
  explanation: string
  provenance: string
  evidenceStatus: 'synthetic_fixture'
}

export const TEACHER_QUESTION_FIXTURES: TeacherQuestionFixture[] = [
  {
    id: 't-q-kinematics-01',
    stem: 'For motion along a straight line, average velocity is:',
    type: 'mcq',
    difficulty: 'foundation',
    bloom: 'Understand',
    competency: 'C1 — conceptual recall (synthetic code)',
    learningOutcome: 'Relate displacement and time for uniform intervals.',
    prerequisite: 'Linear motion definitions',
    rubric: 'Select the definition matching total displacement over total time.',
    options: [
      'Total path length divided by time',
      'Total displacement divided by time',
      'Instantaneous speed at midpoint',
      'Change in acceleration over time',
    ],
    correctAnswer: 'Total displacement divided by time',
    explanation: 'Average velocity uses displacement, not path length.',
    provenance: 'internal-synthetic-2026-demo',
    evidenceStatus: 'synthetic_fixture',
  },
  {
    id: 't-q-kinematics-02',
    stem: 'If $s = 2t^2$ (SI units), magnitude of velocity at $t=3$ s is:',
    type: 'numerical',
    difficulty: 'moderate',
    bloom: 'Apply',
    competency: 'C2 — differentiate basic motion laws (synthetic)',
    learningOutcome: 'Differentiate position to obtain velocity.',
    prerequisite: 'Power rule for derivatives',
    rubric: 'Accept 12 m/s within rounding tolerance.',
    correctAnswer: '12',
    explanation: '$v = ds/dt = 4t$; at $t=3$, $v=12$ m/s.',
    provenance: 'internal-synthetic-2026-demo',
    evidenceStatus: 'synthetic_fixture',
  },
]