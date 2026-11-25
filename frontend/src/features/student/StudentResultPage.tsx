import { SYNTHETIC_STUDENT_RESULT } from '../../fixtures/diagnostics'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function StudentResultPage() {
  const feature = resolveCapabilities().student_results
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Student results (synthetic)</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <p>{SYNTHETIC_STUDENT_RESULT.narrative}</p>
      <p>
        Score: <strong>{SYNTHETIC_STUDENT_RESULT.scorePercent}%</strong> (illustrative)
      </p>
      <ul>
        {SYNTHETIC_STUDENT_RESULT.unknownVsWeak.map((row) => (
          <li key={row.topic}>
            <strong>{row.topic}</strong> — {row.status}: {row.note}
          </li>
        ))}
      </ul>
    </section>
  )
}