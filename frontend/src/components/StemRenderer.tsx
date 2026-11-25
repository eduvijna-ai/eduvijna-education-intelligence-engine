import { parseStemSegments, plainTextAlternative, renderMathHtml } from '../lib/safeRender'

type Props = {
  source: string
  className?: string
}

export function StemRenderer({ source, className }: Props) {
  const segments = parseStemSegments(source)
  const alt = plainTextAlternative(segments)
  return (
    <div className={className}>
      {segments.map((seg, index) => {
        if (seg.kind === 'text') {
          return <span key={index}>{seg.value}</span>
        }
        return (
          <span
            key={index}
            className={seg.display ? 'math-display' : 'math-inline'}
            dangerouslySetInnerHTML={{ __html: renderMathHtml(seg.latex, seg.display) }}
            aria-label={seg.latex}
          />
        )
      })}
      <span className="sr-only">Plain text: {alt}</span>
    </div>
  )
}