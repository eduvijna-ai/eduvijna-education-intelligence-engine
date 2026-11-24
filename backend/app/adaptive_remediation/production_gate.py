"""D16-03 production and runtime containment guards."""

from __future__ import annotations

from typing import Any

from app.adaptive_remediation.containment import (
    CONTAINMENT_NOTE,
    PRODUCTION_REMEDIATION_DISABLED,
)
from app.adaptive_remediation.contracts import ProductionRemediationGate
from app.adaptive_remediation.enums import RemediationVerdict


def production_remediation_gate(*, reason: str | None = None) -> ProductionRemediationGate:
    codes: list[str] = ["D16_PRODUCTION_DISABLED", "DAY15_ON_HOLD"]
    if reason:
        codes.append(reason)
    return ProductionRemediationGate(
        production_ready=False,
        actionable=False,
        delivered_question_count=0,
        validated_question_count=0,
        scheduled_event_count=0,
        persisted_plan_id=None,
        learner_record_touched=False,
        verdict=RemediationVerdict.NOT_READY,
        reason_codes=tuple(codes),
    )


def blocked_production_gate(*, extra_reasons: tuple[str, ...] = ()) -> ProductionRemediationGate:
    codes = ("D16_PRODUCTION_DISABLED", "DAY15_ON_HOLD", *extra_reasons)
    return ProductionRemediationGate(
        production_ready=False,
        actionable=False,
        delivered_question_count=0,
        validated_question_count=0,
        scheduled_event_count=0,
        persisted_plan_id=None,
        learner_record_touched=False,
        verdict=RemediationVerdict.BLOCKED,
        reason_codes=codes,
    )


def explain_containment() -> dict[str, Any]:
    return {
        "production_remediation_disabled": PRODUCTION_REMEDIATION_DISABLED,
        "containment_note": CONTAINMENT_NOTE,
        "day14_academic_validation_preserved": True,
        "day14_issuance_disabled_preserved": True,
    }
