import { SYNTHETIC_TEACHER_DIAGNOSTICS } from '../../fixtures/diagnostics'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function TeacherDiagnosticsPage() {
  const feature = resolveCapabilities().teacher_diagnostics
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Teacher diagnostics dashboard</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <p>{SYNTHETIC_TEACHER_DIAGNOSTICS.classLabel}</p>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Pattern</th>
            <th scope="col">Evidence</th>
            <th scope="col">Share</th>
          </tr>
        </thead>
        <tbody>
          {SYNTHETIC_TEACHER_DIAGNOSTICS.patterns.map((p) => (
            <tr key={p.pattern}>
              <td>{p.pattern}</td>
              <td>{p.evidence}</td>
              <td>{p.share}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}