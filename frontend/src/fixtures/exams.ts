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
  /** Sum of illustrative sample item marks only — not planned profile total. */
  illustrativeSampleMarks: number
  items: SyntheticPaperItem[]
}

export type SyntheticPaperPreview = {
  id: string
  title: string
  disclaimer: string
  plannedTotal: number
  deliveredActual: number
  illustrativeSampleCount: number
  /** Planned profile marks are unknown in this synthetic demo. */
  plannedTotalMarksStatus: 'unknown_synthetic'
  illustrativeSampleMarksTotal: number
  negativeMarking: string
  durationMinutes: number
  sourceStatus: 'synthetic_fixture'
  sections: SyntheticPaperSection[]
}

export type PaperMode = 'single' | 'two_paper'
export type CountContract = 'exact_count' | 'full_paper'

export const EXAM_PACK_FIXTURES = [
  {
    packId: 'generic-demo-pack',
    version: 'v0-synthetic',
    label: 'Generic exam pack (synthetic — not official)',
    readiness: 'source_pending' as const,
    paperMode: 'single' as PaperMode,
    countContract: 'exact_count' as CountContract,
  },
  {
    packId: 'sectional-practice',
    version: 'v0-synthetic',
    label: 'Sectional practice profile (synthetic)',
    readiness: 'diagnostic_only' as const,
    paperMode: 'two_paper' as PaperMode,
    countContract: 'full_paper' as CountContract,
  },
] as const

export const EXAM_VERSIONS: Record<string, { id: string; label: string }[]> = {
  'generic-demo-pack': [{ id: 'v0-synthetic', label: 'Version v0-synthetic' }],
  'sectional-practice': [{ id: 'v0-synthetic', label: 'Version v0-synthetic' }],
}

export const EXAM_SUBJECTS: Record<string, { id: string; label: string }[]> = {
  'generic-demo-pack:v0-synthetic': [
    { id: 'science', label: 'Science (synthetic)' },
    { id: 'mathematics', label: 'Mathematics (synthetic)' },
  ],
  'sectional-practice:v0-synthetic': [
    { id: 'science', label: 'Science (synthetic)' },
    { id: 'mathematics', label: 'Mathematics (synthetic)' },
  ],
}

export const EXAM_SECTIONS: Record<string, { id: string; label: string }[]> = {
  'generic-demo-pack:v0-synthetic:science': [
    { id: 'sec-a', label: 'Section A — conceptual' },
    { id: 'sec-b', label: 'Section B — application' },
  ],
  'generic-demo-pack:v0-synthetic:mathematics': [{ id: 'sec-m1', label: 'Section M1 — quantitative' }],
  'sectional-practice:v0-synthetic:science': [
    { id: 'sec-a', label: 'Section A — conceptual' },
    { id: 'sec-b', label: 'Section B — application' },
  ],
  'sectional-practice:v0-synthetic:mathematics': [{ id: 'sec-m1', label: 'Section M1 — quantitative' }],
}

export const SYNTHETIC_PAPER_PREVIEW: SyntheticPaperPreview = {
  id: 'paper-demo-001',
  title: 'Synthetic full-paper preview (fixed fixture — not user configuration)',
  disclaimer:
    'Fixed illustrative preview only. Delivered count is zero. Sample stems and sample marks do not reflect selected studio configuration or official profiles.',
  plannedTotal: 30,
  deliveredActual: 0,
  illustrativeSampleCount: 3,
  plannedTotalMarksStatus: 'unknown_synthetic',
  illustrativeSampleMarksTotal: 9,
  negativeMarking: 'Demo profile: −1 per incorrect MCQ (not operational)',
  durationMinutes: 180,
  sourceStatus: 'synthetic_fixture',
  sections: [
    {
      title: 'Section A — conceptual',
      plannedCount: 20,
      deliveredActual: 0,
      illustrativeSamples: 2,
      illustrativeSampleMarks: 5,
      items: [
        {
          id: 'demo-a1',
          stemPlain: 'Define average velocity for uniform motion.',
          marks: 2,
          illustrativeSample: true,
        },
        {
          id: 'demo-a2',
          stemPlain:
            'A body moves with position $s = 2t^2$ (SI). Find the magnitude of velocity at $t = 2$ s.',
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
      illustrativeSampleMarks: 4,
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

export function paperModeForPack(packId: string): PaperMode {
  return EXAM_PACK_FIXTURES.find((p) => p.packId === packId)?.paperMode ?? 'single'
}

export function countContractForPack(packId: string): CountContract {
  return EXAM_PACK_FIXTURES.find((p) => p.packId === packId)?.countContract ?? 'exact_count'
}

export const TWO_PAPER_CONTRACT = {
  mode: 'two_paper' as PaperMode,
  paperOneLabel: 'Paper I — synthetic demo',
  paperTwoLabel: 'Paper II — synthetic demo',
  issuance: 'BLOCKED' as const,
}

export function examSubjectKey(packId: string, versionId: string): string {
  return `${packId}:${versionId}`
}

export function examSectionKey(packId: string, versionId: string, subjectId: string): string {
  return `${packId}:${versionId}:${subjectId}`
}