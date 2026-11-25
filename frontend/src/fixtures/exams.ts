export type SyntheticPaperItem = {
  id: string
  stemPlain: string
  marks: number
  illustrativeSample: true
}

export type SyntheticPaperSection = {
  title: string
  plannedCount: number
  /** Issued items — always zero in demo. */
  deliveredActual: number
  /** Fixed sample stems shown for layout only. */
  illustrativeSamples: number
  sectionMarks: number
  items: SyntheticPaperItem[]
}

export type SyntheticPaperPreview = {
  id: string
  title: string
  disclaimer: string
  plannedTotal: number
  deliveredActual: number
  illustrativeSampleCount: number
  totalMarks: number
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
] as const

export const EXAM_VERSIONS: Record<string, { id: string; label: string }[]> = {
  'generic-demo-pack': [{ id: 'v0-synthetic', label: 'Version v0-synthetic' }],
  'sectional-practice': [{ id: 'v0-synthetic', label: 'Version v0-synthetic' }],
}

export const EXAM_SUBJECTS: Record<string, { id: string; label: string }[]> = {
  'v0-synthetic': [
    { id: 'science', label: 'Science (synthetic)' },
    { id: 'mathematics', label: 'Mathematics (synthetic)' },
  ],
}

export const EXAM_SECTIONS: Record<string, { id: string; label: string }[]> = {
  science: [
    { id: 'sec-a', label: 'Section A — conceptual' },
    { id: 'sec-b', label: 'Section B — application' },
  ],
  mathematics: [{ id: 'sec-m1', label: 'Section M1 — quantitative' }],
}

export const SYNTHETIC_PAPER_PREVIEW: SyntheticPaperPreview = {
  id: 'paper-demo-001',
  title: 'Synthetic full-paper preview',
  disclaimer:
    'Configuration preview only. Delivered count is zero; sample stems are illustrative layout fixtures, not issued items.',
  plannedTotal: 30,
  deliveredActual: 0,
  illustrativeSampleCount: 3,
  totalMarks: 9,
  negativeMarking: 'Demo profile: −1 per incorrect MCQ (not operational)',
  durationMinutes: 180,
  sourceStatus: 'synthetic_fixture',
  sections: [
    {
      title: 'Section A — conceptual',
      plannedCount: 20,
      deliveredActual: 0,
      illustrativeSamples: 2,
      sectionMarks: 5,
      items: [
        {
          id: 'demo-a1',
          stemPlain: 'Define average velocity for uniform motion.',
          marks: 2,
          illustrativeSample: true,
        },
        {
          id: 'demo-a2',
          stemPlain: 'A body moves with position given by a quadratic time law. Find velocity at t=2 s.',
          marks: 3,
          illustrativeSample: true,
        },
      ],
    },
    {
      title: 'Section B — application',
      plannedCount: 10,
      deliveredActual: 0,
      illustrativeSamples: 1,
      sectionMarks: 4,
      items: [
        {
          id: 'demo-b1',
          stemPlain: 'Compare displacement and distance for a closed lap.',
          marks: 4,
          illustrativeSample: true,
        },
      ],
    },
  ],
}

export type PaperMode = 'single' | 'two_paper'

export function paperModeForPack(packId: string): PaperMode {
  return packId === 'sectional-practice' ? 'two_paper' : 'single'
}

export const TWO_PAPER_CONTRACT = {
  mode: 'two_paper' as PaperMode,
  paperOneLabel: 'Paper I — synthetic demo',
  paperTwoLabel: 'Paper II — synthetic demo',
  issuance: 'BLOCKED' as const,
}