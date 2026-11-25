import { SYNTHETIC_STUDENT_RESULT } from '../../fixtures/diagnostics'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function StudentDiagnosticsPage() {
  const feature = resolveCapabilities().student_diagnostics
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Student diagnostics (synthetic)</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <ul>
        {SYNTHETIC_STUDENT_RESULT.unknownVsWeak.map((row) => (
          <li key={row.topic}>
            <strong>{row.topic}</strong> — status <code>{row.status}</code>: {row.note}
          </li>
        ))}
      </ul>
    </section>
  )
}