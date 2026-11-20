"""Official hard constraints vs historic soft priors vs practice preferences (D12-16)."""

from __future__ import annotations

from enum import IntEnum

from sqlalchemy.orm import Session

from app.jee_advanced.enums import JeeAdvancedSourceTrustMode
from app.jee_advanced.reference_blueprint import reference_blueprint_issue_codes
from app.jee_advanced.source_authority import evaluate_reference_authority


class ConstraintLayer(IntEnum):
    OFFICIAL_APPROVED = 3
    HISTORICAL_OBSERVED = 2
    TEACHER_PRACTICE_PREFERENCE = 1


def resolve_constraint_layer(
    *,
    trust_mode: JeeAdvancedSourceTrustMode,
    official_rule_pin_present: bool = False,
) -> ConstraintLayer:
    """Non-authority hint only — never grants OFFICIAL_APPROVED from caller flags (AC-F02)."""

    _ = official_rule_pin_present
    if trust_mode == JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026:
        return ConstraintLayer.HISTORICAL_OBSERVED
    return ConstraintLayer.TEACHER_PRACTICE_PREFERENCE


def resolve_authoritative_constraint_layer(
    session: Session,
    *,
    exam_version_id: str,
    trust_mode: JeeAdvancedSourceTrustMode,
) -> tuple[ConstraintLayer, tuple[str, ...]]:
    """Database-backed official precedence — fail-closed without trusted six-slot + blueprint."""

    if trust_mode is not JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026:
        return ConstraintLayer.TEACHER_PRACTICE_PREFERENCE, ()

    authority = evaluate_reference_authority(session)
    issues = list(authority.issues)
    blueprint_issues = reference_blueprint_issue_codes(session, exam_version_id)
    issues.extend(blueprint_issues)
    if not authority.ready or blueprint_issues:
        return ConstraintLayer.HISTORICAL_OBSERVED, tuple(dict.fromkeys(issues))
    return ConstraintLayer.OFFICIAL_APPROVED, ()


def official_overrides_soft_priors(
    session: Session,
    *,
    exam_version_id: str,
    trust_mode: JeeAdvancedSourceTrustMode,
) -> bool:
    layer, _issues = resolve_authoritative_constraint_layer(
        session,
        exam_version_id=exam_version_id,
        trust_mode=trust_mode,
    )
    return layer == ConstraintLayer.OFFICIAL_APPROVED