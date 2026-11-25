"""Shared fail-closed responses for Day15/16 blocked surfaces."""

from __future__ import annotations

from app.platform.errors import CapabilityNotReadyError

LEARNER_HOLD_REASON = "Day15 learner intelligence PR #57 ON_HOLD — no trusted learner processing"
REMEDIATION_HOLD_REASON = "Day16 runtime learner remediation is unconditionally NOT_READY"


def block_learner_capability(capability: str) -> None:
    raise CapabilityNotReadyError(capability=capability, reason=LEARNER_HOLD_REASON)


def block_remediation_capability(capability: str) -> None:
    raise CapabilityNotReadyError(capability=capability, reason=REMEDIATION_HOLD_REASON)
