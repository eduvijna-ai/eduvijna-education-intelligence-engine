import { CapabilityBadge } from '../../components/CapabilityBadge'
import { resolveCapabilities } from '../../capability/readiness'

export function KnowledgeLibraryPage() {
  const feature = resolveCapabilities().knowledge_library
  return (
    <section className="panel">
      <header className="page-header">
        <h2>Knowledge &amp; teacher library</h2>
        <CapabilityBadge state={feature.readiness} />
      </header>
      <p>Search and workspace UI contract — backend RAG unavailable; no fabricated hit lists.</p>
      <label htmlFor="library-search">Search (disabled)</label>
      <input id="library-search" type="search" disabled placeholder="Unavailable" />
    </section>
  )
}