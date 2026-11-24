"""D16-03 production and runtime containment guards."""

from __future__ import annotations

from typing import Any

from app.adaptive_remediation.containment import (
    CONTAINMENT_NOTE,
    FORBIDDEN_RUNTIME_TYPES,
    PRODUCTION_REMEDIATION_DISABLED,
)
from app.adaptive_remediation.contracts import ProductionRemediationGate
from app.adaptive_remediation.enums import RemediationVerdict


def runtime_injection_blocked(*args: object, **kwargs: object) -> tuple[bool, tuple[str, ...]]:
    issues: list[str] = []
    for key in kwargs:
        lowered = key.lower()
        if lowered in {"session", "db", "engine", "provider"}:
            issues.append("RUNTIME_SESSION_INJECTION_BLOCKED")
    for value in (*args, *kwargs.values()):
        if value is None:
            continue
        type_name = f"{type(value).__module__}.{type(value).__qualname__}"
        qualname = type(value).__qualname__
        if type_name in FORBIDDEN_RUNTIME_TYPES or "Session" in qualname:
            issues.append("RUNTIME_SESSION_INJECTION_BLOCKED")
        if _looks_like_orm_instance(value):
            issues.append("ORM_INSTANCE_INPUT_BLOCKED")
    return (len(issues) == 0, tuple(dict.fromkeys(issues)))


def _looks_like_orm_instance(value: object) -> bool:
    module = getattr(type(value), "__module__", "") or ""
    return module.startswith("app.models.") and not isinstance(value, (str, int, float, bool))


def trust_bypass_requested(**kwargs: object) -> tuple[bool, tuple[str, ...]]:
    forbidden_keys = (
        "enable_production",
        "trust_mode_override",
        "synthetic_bypass",
        "harness_authorized",
        "attestation",
        "force_actionable",
    )
    hit = [k for k in forbidden_keys if k in kwargs]
    return (len(hit) == 0, tuple(f"CALLER_TRUST_BYPASS:{k}" for k in hit))


def production_remediation_gate(*, reason: str | None = None) -> ProductionRemediationGate:
    codes = ["D16_PRODUCTION_DISABLED", "DAY15_ON_HOLD"]
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


def explain_containment() -> dict[str, Any]:
    return {
        "production_remediation_disabled": PRODUCTION_REMEDIATION_DISABLED,
        "containment_note": CONTAINMENT_NOTE,
        "day14_academic_validation_preserved": True,
        "day14_issuance_disabled_preserved": True,
    }
