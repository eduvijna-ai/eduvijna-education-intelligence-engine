import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function PolicyAdminPage() {
  const feature = resolveCapabilities().policy_admin
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Policy, RBAC &amp; API keys (contract)</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <p>Non-authoritative permission matrix — Day17 held; no key material displayed.</p>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Role</th>
            <th scope="col">Capability</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>teacher_demo</td>
            <td>question.generate</td>
            <td>blocked</td>
          </tr>
          <tr>
            <td>student_demo</td>
            <td>attempt.submit</td>
            <td>blocked</td>
          </tr>
        </tbody>
      </table>
    </section>
  )
}