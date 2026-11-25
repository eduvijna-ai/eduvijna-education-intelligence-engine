import { assertActionBlocked } from '../capability/readiness'
import type { FeatureKey } from '../capability/types'

type Props = {
  feature: FeatureKey
  actionLabel: string
  disabled?: boolean
  onBlockedAttempt?: (reason: string) => void
}

export function FailClosedAction({ feature, actionLabel, disabled, onBlockedAttempt }: Props) {
  const handleClick = () => {
    const result = assertActionBlocked(feature, actionLabel)
    onBlockedAttempt?.(result.reason)
  }

  return (
    <button
      type="button"
      className="btn btn-blocked"
      disabled={disabled ?? true}
      onClick={handleClick}
      data-testid={`action-blocked-${feature}`}
      aria-disabled="true"
    >
      {actionLabel} (unavailable)
    </button>
  )
}