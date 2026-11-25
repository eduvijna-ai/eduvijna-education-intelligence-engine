export function NonAuthoritativeBanner() {
  return (
    <aside className="non-auth-banner" role="status" data-testid="non-authoritative-banner">
      <strong>Synthetic demonstration</strong>
      <p>
        This UI shows fixed internal fixtures only. It cannot authenticate, issue papers, activate
        sources, or process real learner data while upstream days remain on hold.
      </p>
    </aside>
  )
}