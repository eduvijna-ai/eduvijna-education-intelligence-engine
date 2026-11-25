import { SYNTHETIC_REMEDIATION_STAGES } from '../../fixtures/diagnostics'
import { FailClosedAction } from '../../components/FailClosedAction'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function RemediationPage() {
  const feature = resolveCapabilities().remediation_surface
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Adaptive remediation visualization</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <ol className="stage-list">
        {SYNTHETIC_REMEDIATION_STAGES.map((s) => (
          <li key={s.stage}>
            <strong>{s.stage}</strong> — {s.description}
          </li>
        ))}
      </ol>
      <FailClosedAction feature="remediation_surface" actionLabel="Schedule remediation" />
    </section>
  )
}