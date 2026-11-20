"""Official hard constraints vs historic soft priors vs practice preferences (D12-16)."""

from __future__ import annotations

from enum import IntEnum

from app.jee_advanced.enums import JeeAdvancedSourceTrustMode


class ConstraintLayer(IntEnum):
    OFFICIAL_APPROVED = 3
    HISTORICAL_OBSERVED = 2
    TEACHER_PRACTICE_PREFERENCE = 1


def resolve_constraint_layer(
    *,
    trust_mode: JeeAdvancedSourceTrustMode,
    official_rule_pin_present: bool,
) -> ConstraintLayer:
    if (
        official_rule_pin_present
        and trust_mode == JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026
    ):
        return ConstraintLayer.OFFICIAL_APPROVED
    if trust_mode == JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026:
        return ConstraintLayer.HISTORICAL_OBSERVED
    return ConstraintLayer.TEACHER_PRACTICE_PREFERENCE


def official_overrides_soft_priors(
    *,
    trust_mode: JeeAdvancedSourceTrustMode,
    official_rule_pin_present: bool,
) -> bool:
    return resolve_constraint_layer(
        trust_mode=trust_mode,
        official_rule_pin_present=official_rule_pin_present,
    ) == ConstraintLayer.OFFICIAL_APPROVED