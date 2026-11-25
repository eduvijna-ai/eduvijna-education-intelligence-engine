import type { SyntheticPaperPreview } from '../fixtures/exams'

const WATERMARK = 'SYNTHETIC DEMO — NOT OFFICIAL — EDUVIJNA'

export function buildPrintableHtml(paper: SyntheticPaperPreview): string {
  const body = paper.sections
    .map(
      (section) => `
      <section>
        <h2>${escape(section.title)}</h2>
        <p>Planned items: ${section.plannedCount} · Delivered (demo): ${section.deliveredCount}</p>
        <ol>
          ${section.items
            .map(
              (item) =>
                `<li><strong>${escape(item.stemPlain)}</strong> (${item.marks} marks)</li>`,
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
  ${body}
  <p class="noprint"><em>Demo export only — no learner data or official issuance.</em></p>
</body>
</html>`
}

export function buildJsonExport(paper: SyntheticPaperPreview): string {
  const payload = {
    watermark: WATERMARK,
    synthetic: true,
    official: false,
    paper: {
      id: paper.id,
      title: paper.title,
      plannedTotal: paper.plannedTotal,
      deliveredTotal: paper.deliveredTotal,
      sections: paper.sections.map((s) => ({
        title: s.title,
        plannedCount: s.plannedCount,
        deliveredCount: s.deliveredCount,
        itemIds: s.items.map((i) => i.id),
      })),
    },
  }
  return JSON.stringify(payload, null, 2)
}

function escape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}