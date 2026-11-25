export type CurriculumSelections = {
  framework: string
  academicVersion: string
  grade: string
  medium: string
  subject: string
  unit: string
  chapter: string
  topic: string
  concept: string
}

export type ScopeLevel = keyof CurriculumSelections

export const SCOPE_LEVEL_ORDER: ScopeLevel[] = [
  'framework',
  'academicVersion',
  'grade',
  'medium',
  'subject',
  'unit',
  'chapter',
  'topic',
  'concept',
]

type Option = { id: string; label: string }

const TREE: Record<ScopeLevel, Option[] | Record<string, Option[]>> = {
  framework: [{ id: 'ncf-demo', label: 'NCF-aligned demo framework (synthetic)' }],
  academicVersion: {
    'ncf-demo': [{ id: 'acad-v2024-demo', label: 'Academic version 2024-demo' }],
  },
  grade: {
    'acad-v2024-demo': [{ id: 'grade-10', label: 'Grade 10' }],
  },
  medium: {
    'grade-10': [
      { id: 'medium-en', label: 'English medium' },
      { id: 'medium-hi', label: 'Hindi medium (synthetic)' },
    ],
  },
  subject: {
    'medium-en': [{ id: 'science', label: 'Science' }],
    'medium-hi': [{ id: 'science', label: 'Science' }],
  },
  unit: {
    science: [{ id: 'unit-motion', label: 'Unit: Motion' }],
  },
  chapter: {
    'unit-motion': [{ id: 'ch-kinematics', label: 'Chapter: Kinematics' }],
  },
  topic: {
    'ch-kinematics': [{ id: 'topic-velocity', label: 'Topic: Velocity' }],
  },
  concept: {
    'topic-velocity': [{ id: 'concept-displacement', label: 'Concept: Displacement vs distance' }],
  },
}

export const EMPTY_SCOPE: CurriculumSelections = {
  framework: '',
  academicVersion: '',
  grade: '',
  medium: '',
  subject: '',
  unit: '',
  chapter: '',
  topic: '',
  concept: '',
}

export function optionsForLevel(
  level: ScopeLevel,
  selections: CurriculumSelections,
): Option[] {
  const node = TREE[level]
  if (Array.isArray(node)) return node
  const parentLevel = SCOPE_LEVEL_ORDER[SCOPE_LEVEL_ORDER.indexOf(level) - 1]
  if (!parentLevel) return []
  const parentValue = selections[parentLevel]
  if (!parentValue) return []
  return node[parentValue] ?? []
}

export function isScopeComplete(selections: CurriculumSelections): boolean {
  return isScopeValid(selections)
}

/** Every selected level must be a valid child of its parent in the fixture tree. */
export function isScopeValid(selections: CurriculumSelections): boolean {
  for (let i = 0; i < SCOPE_LEVEL_ORDER.length; i += 1) {
    const level = SCOPE_LEVEL_ORDER[i]
    const value = selections[level]
    if (!value) return false
    const allowed = optionsForLevel(level, selections)
    if (!allowed.some((o) => o.id === value)) return false
  }
  return true
}

export function resetDependents(
  selections: CurriculumSelections,
  changedLevel: ScopeLevel,
): CurriculumSelections {
  const idx = SCOPE_LEVEL_ORDER.indexOf(changedLevel)
  const next = { ...selections }
  for (let i = idx + 1; i < SCOPE_LEVEL_ORDER.length; i += 1) {
    next[SCOPE_LEVEL_ORDER[i]] = ''
  }
  return next
}