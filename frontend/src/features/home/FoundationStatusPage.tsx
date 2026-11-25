import { useEffect, useState } from 'react'

import { getSystemInfo } from '../../api/system'
import { probeHealth } from '../../api/health'
import { resolveCapabilities } from '../../capability/readiness'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import type { SystemInfo } from '../../types/system'

export function FoundationStatusPage() {
  const caps = resolveCapabilities({
    urlSearch: window.location.search,
    storageSnapshot: {},
    mockFlag: true,
    callerPrivilege: 'admin',
  })
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [health, setHealth] = useState<string>('…')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      getSystemInfo(controller.signal).catch((e: unknown) => {
        if (e instanceof DOMException && e.name === 'AbortError') return null
        throw e
      }),
      probeHealth(controller.signal),
    ])
      .then(([info, probe]) => {
        setSystem(info)
        setHealth(probe.detail)
        setError(info ? null : 'System info unavailable')
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : 'Unable to reach backend')
      })
    return () => controller.abort()
  }, [])

  return (
    <section className="panel">
      <header className="page-header">
        <h2>Foundation status</h2>
        <p className="lede">Connection probes are distinct from feature readiness.</p>
      </header>
      <dl className="status-grid">
        <div>
          <dt>Backend connection</dt>
          <dd className={system ? 'ok' : error ? 'error' : 'pending'}>
            {system ? 'Connected' : error ? 'Unavailable' : 'Connecting…'}
          </dd>
        </div>
        <div>
          <dt>Health probe</dt>
          <dd>{health}</dd>
        </div>
        <div>
          <dt>Feature readiness</dt>
          <dd>
            <CapabilityBadge state="diagnostic_only" /> (fixed policy)
          </dd>
        </div>
        <div>
          <dt>Environment</dt>
          <dd>{system?.environment ?? '—'}</dd>
        </div>
        <div>
          <dt>API version</dt>
          <dd>{system?.api_version ?? '—'}</dd>
        </div>
      </dl>
      {error ? <p className="error-copy">{error}</p> : null}
      <section aria-labelledby="cap-matrix">
        <h3 id="cap-matrix">Capability matrix (default deny)</h3>
        <ul className="cap-list">
          {Object.values(caps).map((c) => (
            <li key={c.key}>
              <strong>{c.label}</strong> <CapabilityBadge state={c.readiness} />
              <span className="muted">{c.rationale}</span>
            </li>
          ))}
        </ul>
      </section>
    </section>
  )
}