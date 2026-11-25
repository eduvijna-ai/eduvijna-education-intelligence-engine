import type { ReadinessState } from '../capability/types'

const LABELS: Record<ReadinessState, string> = {
  unavailable: 'Unavailable',
  blocked: 'Blocked',
  source_pending: 'Source pending',
  diagnostic_only: 'Diagnostic demo',
  connection_only: 'Connection probe',
}

type Props = { state: ReadinessState }

export function CapabilityBadge({ state }: Props) {
  return (
    <span className={`cap-badge cap-${state}`} data-testid={`capability-${state}`}>
      {LABELS[state]}
    </span>
  )
}