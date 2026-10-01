import { useEffect, useState } from 'react'

import { getSystemInfo } from '../api/system'
import type { SystemInfo } from '../types/system'

export function HomePage() {
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getSystemInfo(controller.signal)
      .then((payload) => {
        setSystem(payload)
        setError(null)
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : 'Unable to reach backend')
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">EDUVIJNA</p>
        <h1>Education Intelligence Engine</h1>
        <p className="lede">
          Curriculum, examination, knowledge, question, diagnostic and learner intelligence —
          built on an auditable platform foundation.
        </p>
      </section>

      <section className="status-card" aria-live="polite">
        <h2>Local foundation status</h2>
        <dl>
          <div>
            <dt>Backend</dt>
            <dd className={system ? 'ok' : error ? 'error' : 'pending'}>
              {system ? 'Connected' : error ? 'Unavailable' : 'Connecting…'}
            </dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{system?.environment ?? '—'}</dd>
          </div>
          <div>
            <dt>API</dt>
            <dd>{system?.api_version ?? '—'}</dd>
          </div>
        </dl>
        {error ? <p className="error-copy">{error}</p> : null}
      </section>
    </main>
  )
}
