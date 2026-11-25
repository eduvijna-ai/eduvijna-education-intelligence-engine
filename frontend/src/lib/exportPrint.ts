import type { SyntheticPaperPreview } from '../fixtures/exams'

const WATERMARK = 'SYNTHETIC DEMO — NOT OFFICIAL — EDUVIJNA'

export function buildPrintableHtml(paper: SyntheticPaperPreview): string {
  const body = paper.sections
    .map(
      (section) => `
      <section>
        <h2>${escape(section.title)}</h2>
        <p>Planned: ${section.plannedCount} · Delivered actual: ${section.deliveredActual} · Illustrative samples: ${section.illustrativeSamples} · Section marks: ${section.sectionMarks}</p>
        <ol>
          ${section.items
            .map(
              (item) =>
                `<li><strong>${escape(item.stemPlain)}</strong> (${item.marks} marks, illustrative sample)</li>`,
            )
            .join('')}
        </ol>
      </section>`,
    )
    .join('')
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>${escape(paper.title)} — ${WATERMARK}</title>
  <style>
    body { font-family: Georgia, serif; padding: 2rem; color: #111; }
    .banner { border: 2px dashed #b42318; padding: 1rem; margin-bottom: 1.5rem; font-weight: bold; }
    @media print { .noprint { display: none; } }
  </style>
</head>
<body>
  <div class="banner" role="status">${WATERMARK}</div>
  <h1>${escape(paper.title)}</h1>
  <p>${escape(paper.disclaimer)}</p>
  <p>Duration: ${paper.durationMinutes} minutes · Total marks (planned profile): ${paper.totalMarks} · Negative marking: ${escape(paper.negativeMarking)}</p>
  ${body}
  <p class="noprint"><em>Demo export only — no learner data, answer keys, or official issuance.</em></p>
</body>
</html>`
}

export function buildJsonExport(paper: SyntheticPaperPreview): string {
  const payload = {
    watermark: WATERMARK,
    synthetic: true,
    official: false,
    deliveredActual: paper.deliveredActual,
    illustrativeSampleCount: paper.illustrativeSampleCount,
    paper: {
      id: paper.id,
      title: paper.title,
      durationMinutes: paper.durationMinutes,
      negativeMarking: paper.negativeMarking,
      plannedTotal: paper.plannedTotal,
      totalMarks: paper.totalMarks,
      sections: paper.sections.map((s) => ({
        title: s.title,
        plannedCount: s.plannedCount,
        deliveredActual: s.deliveredActual,
        illustrativeSamples: s.illustrativeSamples,
        sectionMarks: s.sectionMarks,
        items: s.items.map((i) => ({
          id: i.id,
          stemPlain: i.stemPlain,
          marks: i.marks,
          illustrativeSample: i.illustrativeSample,
        })),
      })),
    },
  }
  return JSON.stringify(payload, null, 2)
}

export function triggerBlobDownload(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function escape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}