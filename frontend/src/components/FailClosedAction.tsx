import { assertActionBlocked } from '../capability/readiness'
import type { FeatureKey } from '../capability/types'

type Props = {
  feature: FeatureKey
  actionLabel: string
  onBlockedAttempt?: (reason: string) => void
}

export function FailClosedAction({ feature, actionLabel, onBlockedAttempt }: Props) {
  const explain = () => {
    const result = assertActionBlocked(feature, actionLabel)
    onBlockedAttempt?.(result.reason)
  }

  return (
    <div className="fail-closed-wrap">
      <button
        type="button"
        className="btn"
        disabled
        aria-disabled="true"
        data-testid={`action-blocked-${feature}`}
      >
        {actionLabel}
      </button>
      <button
        type="button"
        className="btn btn-muted"
        onClick={explain}
        data-testid={`explain-blocked-${feature}`}
      >
        Why unavailable
      </button>
    </div>
  )
}