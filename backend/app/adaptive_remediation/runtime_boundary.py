"""D16 public runtime boundary — fail closed before any caller input is processed."""

from __future__ import annotations

from app.adaptive_remediation.containment import CONTAINMENT_NOTE, SYNTHETIC_DIAGNOSTIC_ONLY
from app.adaptive_remediation.contracts import AdaptiveRemediationPlan
from app.adaptive_remediation.enums import AdaptationDecision, RemediationVerdict
from app.adaptive_remediation.production_gate import blocked_production_gate


def _caller_payload_present(*args: object, **kwargs: object) -> bool:
    if args or kwargs:
        return True
    return False


def blocked_runtime_plan(*, injection_attempted: bool = False) -> AdaptiveRemediationPlan:
    """Return empty non-actionable plan with no caller-derived fields."""
    reason = "RUNTIME_INPUT_REJECTED" if injection_attempted else "RUNTIME_ENTRY_NOT_AUTHORIZED"
    gate = blocked_production_gate(extra_reasons=(reason,))
    return AdaptiveRemediationPlan(
        plan_id="d16-runtime-blocked",
        fingerprint="d16-runtime-blocked-fingerprint",
        verdict=RemediationVerdict.BLOCKED if injection_attempted else RemediationVerdict.NOT_READY,
        policy_version="d16-adaptive-policy-v1",
        targets=(),
        stages=(),
        requested_count=0,
        planned_count=0,
        selected_count=0,
        explanation="Production remediation entry is disabled; no caller data processed.",
        adaptation_decision=AdaptationDecision.INSUFFICIENT_EVIDENCE,
        production_gate=gate,
        metadata_json={
            "synthetic_diagnostic_only": SYNTHETIC_DIAGNOSTIC_ONLY,
            "containment_note": CONTAINMENT_NOTE,
            "non_actionable": True,
            "caller_data_processed": False,
        },
    )


def attempt_runtime_remediation(*args: object, **kwargs: object) -> AdaptiveRemediationPlan:
    """Public remediation entry — unconditionally rejects without reading input values."""
    if _caller_payload_present(*args, **kwargs):
        return blocked_runtime_plan(injection_attempted=True)
    return blocked_runtime_plan(injection_attempted=False)
