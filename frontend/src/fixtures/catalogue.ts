/** Internal synthetic fixture catalogue (D18-33) — demo mode is not caller-switchable. */
export const FIXTURE_CATALOGUE_META = {
  authored: 'eduvijna-internal-synthetic-v1',
  authoritative: false,
  pii: false,
  credentials: false,
  answerKeysInStudentBundle: false,
} as const

export type DesignRoleFixture = 'teacher' | 'student' | 'admin_viewer'

export const DESIGN_ROLE_FIXTURES: ReadonlyArray<{
  id: DesignRoleFixture
  label: string
  nonAuthoritative: true
}> = [
  { id: 'teacher', label: 'Teacher workspace (design)', nonAuthoritative: true },
  { id: 'student', label: 'Student workspace (design)', nonAuthoritative: true },
  { id: 'admin_viewer', label: 'Admin viewer (design)', nonAuthoritative: true },
]