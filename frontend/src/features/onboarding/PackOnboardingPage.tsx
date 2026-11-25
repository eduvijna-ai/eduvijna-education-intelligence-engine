import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function PackOnboardingPage() {
  const feature = resolveCapabilities().pack_onboarding
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Exam / curriculum pack onboarding</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <form className="onboarding-form" onSubmit={(e) => e.preventDefault()}>
        <label htmlFor="pack-name">Pack name (no write)</label>
        <input id="pack-name" disabled />
        <label htmlFor="pack-version">Version label</label>
        <input id="pack-version" disabled />
        <button type="submit" disabled>
          Save pack (blocked)
        </button>
      </form>
    </section>
  )
}