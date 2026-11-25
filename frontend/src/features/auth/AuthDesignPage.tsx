import { INERT_AUTH_CONTRACT } from '../../contracts/day17-inert'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function AuthDesignPage() {
  const auth = resolveCapabilities().auth_design
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Authentication surfaces (design only)</h2>
        <CapabilityBadge state={auth.readiness} />
      </header>
      <p>
        Login, logout, and session-expiry layouts are shown as contracts only. Day17 auth is on hold —
        no credential fields submit data.
      </p>
      <form className="auth-form" onSubmit={(e) => e.preventDefault()} aria-label="Login design mock">
        <label htmlFor="email-design">Email (not captured)</label>
        <input id="email-design" type="text" autoComplete="off" disabled readOnly value="" />
        <label htmlFor="password-design">Password (not captured)</label>
        <input id="password-design" type="password" autoComplete="off" disabled readOnly value="" />
        <button type="submit" disabled data-testid="login-submit-disabled">
          Sign in (blocked)
        </button>
      </form>
      <dl className="status-grid">
        <div>
          <dt>Authenticated</dt>
          <dd>{String(INERT_AUTH_CONTRACT.authenticated)}</dd>
        </div>
        <div>
          <dt>Day17 status</dt>
          <dd>{INERT_AUTH_CONTRACT.day17_status}</dd>
        </div>
      </dl>
    </section>
  )
}