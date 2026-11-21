from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.jee_advanced.constants import VERSION_CANDIDATE_2027, VERSION_REFERENCE_2026
from app.jee_advanced.enums import (
    AdvancedIssueCode,
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.source_registry import reference_evidence_ready


@dataclass(frozen=True, slots=True)
class ProfileAuthorityDecision:
    trust_mode: JeeAdvancedSourceTrustMode
    verdict: AdvancedPlanVerdict | None
    issue_codes: tuple[AdvancedIssueCode, ...]
    allow_reference_replica: bool
    allow_official_2027_replica: bool


def resolve_profile_authority(
    *,
    profile_kind: AdvancedProfileKind,
    academic_year: str,
    session: Session | None = None,
) -> ProfileAuthorityDecision:
    """D12-05: 2026 reference vs 2027 candidate authority (fail-closed)."""

    reference_sources_approved = reference_evidence_ready(session)

    if profile_kind is AdvancedProfileKind.CANDIDATE_2027 or academic_year == "2027":
        return ProfileAuthorityDecision(
            trust_mode=JeeAdvancedSourceTrustMode.OFFICIAL_2027_NOT_VERIFIED,
            verdict=AdvancedPlanVerdict.OFFICIAL_PATTERN_NOT_VERIFIED,
            issue_codes=(AdvancedIssueCode.UNAPPROVED_SOURCE,),
            allow_reference_replica=False,
            allow_official_2027_replica=False,
        )

    if profile_kind is AdvancedProfileKind.SYNTHETIC_DEMO:
        return ProfileAuthorityDecision(
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            verdict=None,
            issue_codes=(),
            allow_reference_replica=False,
            allow_official_2027_replica=False,
        )

    if profile_kind is AdvancedProfileKind.REFERENCE_2026:
        if not reference_sources_approved:
            return ProfileAuthorityDecision(
                trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
                verdict=AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED,
                issue_codes=(AdvancedIssueCode.UNAPPROVED_SOURCE,),
                allow_reference_replica=False,
                allow_official_2027_replica=False,
            )
        return ProfileAuthorityDecision(
            trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
            verdict=None,
            issue_codes=(),
            allow_reference_replica=True,
            allow_official_2027_replica=False,
        )

    return ProfileAuthorityDecision(
        trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
        verdict=AdvancedPlanVerdict.REVIEW_REQUIRED,
        issue_codes=(AdvancedIssueCode.WRONG_VERSION_YEAR,),
        allow_reference_replica=False,
        allow_official_2027_replica=False,
    )


def version_code_for_profile(profile_kind: AdvancedProfileKind) -> str:
    mapping = {
        AdvancedProfileKind.SYNTHETIC_DEMO: "synthetic-demo-v1",
        AdvancedProfileKind.REFERENCE_2026: VERSION_REFERENCE_2026,
        AdvancedProfileKind.CANDIDATE_2027: VERSION_CANDIDATE_2027,
    }
    return mapping[profile_kind]
