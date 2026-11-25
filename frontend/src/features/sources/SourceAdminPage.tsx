import { useState } from 'react'

import { FailClosedAction } from '../../components/FailClosedAction'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function SourceAdminPage() {
  const feature = resolveCapabilities().source_admin
  const [blockReason, setBlockReason] = useState<string | null>(null)
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Source administration</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <p>Registry, revision, diff, and activation surfaces show blocked status — live intake disabled.</p>
      <FailClosedAction feature="source_admin" actionLabel="Upload source" onBlockedAttempt={setBlockReason} />
      <FailClosedAction feature="source_admin" actionLabel="Activate revision" onBlockedAttempt={setBlockReason} />
      {blockReason ? (
        <p className="error-copy" role="status" data-testid="blocked-reason">
          {blockReason}
        </p>
      ) : null}
    </section>
  )
}