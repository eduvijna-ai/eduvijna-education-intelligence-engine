import katex from 'katex'

const HTML_ESCAPE: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => HTML_ESCAPE[ch] ?? ch)
}

export type RenderSegment =
  | { kind: 'text'; value: string }
  | { kind: 'math'; latex: string; display: boolean }

/** Split fixture text on $...$ and $$...$$ — fixture-authored only. */
export function parseStemSegments(source: string): RenderSegment[] {
  const segments: RenderSegment[] = []
  let i = 0
  while (i < source.length) {
    if (source.startsWith('$$', i)) {
      const end = source.indexOf('$$', i + 2)
      if (end === -1) {
        segments.push({ kind: 'text', value: source.slice(i) })
        break
      }
      segments.push({ kind: 'math', latex: source.slice(i + 2, end), display: true })
      i = end + 2
      continue
    }
    if (source[i] === '$') {
      const end = source.indexOf('$', i + 1)
      if (end === -1) {
        segments.push({ kind: 'text', value: source.slice(i) })
        break
      }
      segments.push({ kind: 'math', latex: source.slice(i + 1, end), display: false })
      i = end + 1
      continue
    }
    const next = source.slice(i).search(/\$\$|\$/)
    const chunkEnd = next === -1 ? source.length : i + next
    segments.push({ kind: 'text', value: source.slice(i, chunkEnd) })
    i = chunkEnd
  }
  return segments
}

export function renderMathHtml(latex: string, display: boolean): string {
  try {
    return katex.renderToString(latex, {
      displayMode: display,
      throwOnError: true,
      trust: false,
      strict: 'error',
      output: 'html',
    })
  } catch {
    return `<span class="math-error" role="alert">[math unavailable]</span>`
  }
}

export function plainTextAlternative(segments: RenderSegment[]): string {
  return segments
    .map((s) => (s.kind === 'text' ? s.value : s.latex))
    .join(' ')
    .trim()
}