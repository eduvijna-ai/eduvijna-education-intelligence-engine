from __future__ import annotations

from typing import Any

from app.education_intelligence.enums import ValidationSeverity, ValidationStatus


def rule_outcome_from_metadata(
    rule: dict[str, Any],
    *,
    triggered: bool,
) -> tuple[ValidationStatus, ValidationSeverity, bool]:
    if not triggered:
        return ValidationStatus.PASS, ValidationSeverity.ADVISORY, False
    severity_raw = str(rule.get("severity", ValidationSeverity.MANDATORY.value))
    try:
        severity = ValidationSeverity(severity_raw)
    except ValueError:
        severity = ValidationSeverity.MANDATORY
    default_blocking = severity in {
        ValidationSeverity.MANDATORY,
        ValidationSeverity.SAFETY,
    }
    blocking = bool(rule.get("blocking", default_blocking))
    if blocking:
        return ValidationStatus.FAIL, severity, True
    if severity == ValidationSeverity.ADVISORY:
        return ValidationStatus.WARN, severity, False
    return ValidationStatus.REVIEW_REQUIRED, severity, False
