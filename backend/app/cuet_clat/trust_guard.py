from __future__ import annotations

from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode


def validate_trust_coherence(
    *,
    profile_kind: CuetClatProfileKind,
    trust_mode: CuetClatSourceTrustMode,
    academic_year: str,
    exam_family: str,
) -> list[IssueCode]:
    issues: list[IssueCode] = []

    if exam_family == "cuet":
        if profile_kind in (CuetClatProfileKind.CLAT_2027,):
            issues.append(IssueCode.WRONG_EXAM_PACK)
        if profile_kind is CuetClatProfileKind.SYNTHETIC_DEMO:
            if trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
                issues.append(IssueCode.UNAPPROVED_SOURCE)
            return issues
        if profile_kind is CuetClatProfileKind.CUET_CANDIDATE_2027:
            if academic_year != "2027":
                issues.append(IssueCode.WRONG_YEAR)
            if trust_mode is not CuetClatSourceTrustMode.CUET_2027_NOT_VERIFIED:
                issues.append(IssueCode.UNAPPROVED_SOURCE)
        elif profile_kind is CuetClatProfileKind.CUET_REFERENCE_2026:
            if academic_year != "2026":
                issues.append(IssueCode.WRONG_YEAR)
            if trust_mode is not CuetClatSourceTrustMode.CUET_HISTORICAL_2026:
                issues.append(IssueCode.UNAPPROVED_SOURCE)
        return issues

    if exam_family == "clat":
        if profile_kind in (
            CuetClatProfileKind.CUET_REFERENCE_2026,
            CuetClatProfileKind.CUET_CANDIDATE_2027,
        ):
            issues.append(IssueCode.WRONG_EXAM_PACK)
        if profile_kind is CuetClatProfileKind.SYNTHETIC_DEMO:
            if trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
                issues.append(IssueCode.UNAPPROVED_SOURCE)
            return issues
        if profile_kind is CuetClatProfileKind.CLAT_2027:
            if academic_year != "2027":
                issues.append(IssueCode.WRONG_YEAR)
            if trust_mode is CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
                issues.append(IssueCode.UNAPPROVED_SOURCE)
            elif trust_mode is not CuetClatSourceTrustMode.CLAT_OFFICIAL_2027:
                issues.append(IssueCode.UNAPPROVED_SOURCE)

    return issues