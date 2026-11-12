from __future__ import annotations

from app.jee_advanced.enums import (
    AdvancedIssueCode,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)


def validate_trust_coherence(
    *,
    profile_kind: AdvancedProfileKind,
    trust_mode: JeeAdvancedSourceTrustMode,
    academic_year: str,
) -> list[AdvancedIssueCode]:
    """Reject caller trust flags that contradict profile/year authority."""

    issues: list[AdvancedIssueCode] = []
    year = academic_year.strip()

    if profile_kind is AdvancedProfileKind.SYNTHETIC_DEMO:
        if trust_mode is not JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE:
            issues.append(AdvancedIssueCode.TRUST_PROFILE_MISMATCH)
        if year == "2027":
            issues.append(AdvancedIssueCode.WRONG_VERSION_YEAR)
        return issues

    if profile_kind is AdvancedProfileKind.REFERENCE_2026:
        if trust_mode is not JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026:
            issues.append(AdvancedIssueCode.TRUST_PROFILE_MISMATCH)
        if year != "2026":
            issues.append(AdvancedIssueCode.WRONG_VERSION_YEAR)
        return issues

    if profile_kind is AdvancedProfileKind.CANDIDATE_2027:
        if trust_mode is not JeeAdvancedSourceTrustMode.OFFICIAL_2027_NOT_VERIFIED:
            issues.append(AdvancedIssueCode.TRUST_PROFILE_MISMATCH)
        return issues

    issues.append(AdvancedIssueCode.WRONG_VERSION_YEAR)
    return issues
