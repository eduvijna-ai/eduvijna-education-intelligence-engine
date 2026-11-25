export type CurriculumNode = {
  id: string
  label: string
  synthetic: true
  children?: CurriculumNode[]
}

export const CURRICULUM_FIXTURE: CurriculumNode = {
  id: 'ncf-demo',
  label: 'NCF-aligned demo framework (synthetic)',
  synthetic: true,
  children: [
    {
      id: 'grade-10',
      label: 'Grade 10 — demo',
      synthetic: true,
      children: [
        {
          id: 'sci',
          label: 'Science',
          synthetic: true,
          children: [
            {
              id: 'unit-motion',
              label: 'Unit: Motion',
              synthetic: true,
              children: [
                {
                  id: 'ch-kinematics',
                  label: 'Chapter: Kinematics',
                  synthetic: true,
                  children: [
                    { id: 'topic-velocity', label: 'Topic: Velocity', synthetic: true },
                  ],
                },
              ],
            },
          ],
        },
      ],
    },
  ],
}

export function flattenSelectablePaths(
  root: CurriculumNode,
  trail: string[] = [],
): Array<{ path: string[]; label: string }> {
  const currentTrail = [...trail, root.label]
  const rows: Array<{ path: string[]; label: string }> = [
    { path: currentTrail, label: currentTrail.join(' › ') },
  ]
  for (const child of root.children ?? []) {
    rows.push(...flattenSelectablePaths(child, currentTrail))
  }
  return rows
}