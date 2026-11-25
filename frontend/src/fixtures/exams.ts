export type SyntheticPaperItem = {
  id: string
  stemPlain: string
  marks: number
}

export type SyntheticPaperSection = {
  title: string
  plannedCount: number
  deliveredCount: number
  items: SyntheticPaperItem[]
}

export type SyntheticPaperPreview = {
  id: string
  title: string
  disclaimer: string
  plannedTotal: number
  deliveredTotal: number
  negativeMarking: string
  durationMinutes: number
  sourceStatus: 'synthetic_fixture'
  sections: SyntheticPaperSection[]
}

export const EXAM_PACK_FIXTURES = [
  {
    packId: 'generic-demo-pack',
    version: 'v0-synthetic',
    label: 'Generic exam pack (synthetic — not official)',
    readiness: 'source_pending' as const,
  },
  {
    packId: 'sectional-practice',
    version: 'v0-synthetic',
    label: 'Sectional practice profile (synthetic)',
    readiness: 'diagnostic_only' as const,
  },
]

export const SYNTHETIC_PAPER_PREVIEW: SyntheticPaperPreview = {
  id: 'paper-demo-001',
  title: 'Synthetic full-paper preview',
  disclaimer:
    'Planned versus delivered counts are illustrative. This is not an official exam paper.',
  plannedTotal: 30,
  deliveredTotal: 3,
  negativeMarking: 'Demo profile: −1 per incorrect MCQ (not operational)',
  durationMinutes: 180,
  sourceStatus: 'synthetic_fixture',
  sections: [
    {
      title: 'Section A — conceptual',
      plannedCount: 20,
      deliveredCount: 2,
      items: [
        {
          id: 'demo-a1',
          stemPlain: 'Define average velocity for uniform motion.',
          marks: 2,
        },
        {
          id: 'demo-a2',
          stemPlain: 'A body moves $s = 4t^2$ m. Find $v$ at $t=2$ s.',
          marks: 3,
        },
      ],
    },
    {
      title: 'Section B — application',
      plannedCount: 10,
      deliveredCount: 1,
      items: [
        {
          id: 'demo-b1',
          stemPlain: 'Compare displacement and distance for a closed lap.',
          marks: 4,
        },
      ],
    },
  ],
}

export type PaperMode = 'single' | 'two_paper'

export const TWO_PAPER_CONTRACT = {
  mode: 'two_paper' as PaperMode,
  paperOneLabel: 'Paper I — synthetic demo',
  paperTwoLabel: 'Paper II — synthetic demo',
  issuance: 'BLOCKED' as const,
}