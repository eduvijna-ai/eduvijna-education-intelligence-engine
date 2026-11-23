from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.cuet_clat.enums import (
    CuetClatProfileKind,
    CuetClatSourceTrustMode,
    IssueCode,
    PlanVerdict,
)
from app.cuet_clat.source_registry import (
    clat_official_evidence_ready,
    cuet_reference_evidence_ready,
)


@dataclass(frozen=True, slots=True)
class ProfileAuthorityDecision:
    trust_mode: CuetClatSourceTrustMode
    verdict: PlanVerdict | None
    issue_codes: tuple[IssueCode, ...]
    allow_official_cuet_replica: bool
    allow_official_clat_replica: bool


def resolve_cuet_authority(
    *,
    profile_kind: CuetClatProfileKind,
    academic_year: str,
    session: Session | None = None,
) -> ProfileAuthorityDecision:
    """D13-05/14: CUET 2026 reference vs 2027 fail-closed."""

    if profile_kind is CuetClatProfileKind.CUET_CANDIDATE_2027 or academic_year == "2027":
        return ProfileAuthorityDecision(
            trust_mode=CuetClatSourceTrustMode.CUET_2027_NOT_VERIFIED,
            verdict=PlanVerdict.OFFICIAL_NOT_VERIFIED,
            issue_codes=(IssueCode.CUET_2027_UNVERIFIED, IssueCode.UNAPPROVED_SOURCE),
            allow_official_cuet_replica=False,
            allow_official_clat_replica=False,
        )

    if profile_kind is CuetClatProfileKind.SYNTHETIC_DEMO:
        return ProfileAuthorityDecision(
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            verdict=None,
            issue_codes=(),
            allow_official_cuet_replica=False,
            allow_official_clat_replica=False,
        )

    if profile_kind is CuetClatProfileKind.CUET_REFERENCE_2026:
        if not cuet_reference_evidence_ready(session):
            return ProfileAuthorityDecision(
                trust_mode=CuetClatSourceTrustMode.CUET_HISTORICAL_2026,
                verdict=PlanVerdict.SOURCE_PENDING,
                issue_codes=(IssueCode.UNAPPROVED_SOURCE,),
                allow_official_cuet_replica=False,
                allow_official_clat_replica=False,
            )
        return ProfileAuthorityDecision(
            trust_mode=CuetClatSourceTrustMode.CUET_HISTORICAL_2026,
            verdict=None,
            issue_codes=(),
            allow_official_cuet_replica=True,
            allow_official_clat_replica=False,
        )

    return ProfileAuthorityDecision(
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        verdict=PlanVerdict.REVIEW_REQUIRED,
        issue_codes=(IssueCode.WRONG_YEAR,),
        allow_official_cuet_replica=False,
        allow_official_clat_replica=False,
    )


def resolve_clat_authority(
    *,
    profile_kind: CuetClatProfileKind,
    academic_year: str,
    session: Session | None = None,
) -> ProfileAuthorityDecision:
    """D13-15: CLAT UG 2027 authority; synthetic allowed without curator bytes."""

    if profile_kind is CuetClatProfileKind.SYNTHETIC_DEMO:
        return ProfileAuthorityDecision(
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            verdict=None,
            issue_codes=(),
            allow_official_cuet_replica=False,
            allow_official_clat_replica=False,
        )

    if profile_kind is CuetClatProfileKind.CLAT_2027 and academic_year == "2027":
        if not clat_official_evidence_ready(session):
            return ProfileAuthorityDecision(
                trust_mode=CuetClatSourceTrustMode.CLAT_OFFICIAL_2027,
                verdict=PlanVerdict.SOURCE_PENDING,
                issue_codes=(IssueCode.UNAPPROVED_SOURCE,),
                allow_official_cuet_replica=False,
                allow_official_clat_replica=False,
            )
        return ProfileAuthorityDecision(
            trust_mode=CuetClatSourceTrustMode.CLAT_OFFICIAL_2027,
            verdict=None,
            issue_codes=(),
            allow_official_cuet_replica=False,
            allow_official_clat_replica=True,
        )

    return ProfileAuthorityDecision(
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        verdict=PlanVerdict.REVIEW_REQUIRED,
        issue_codes=(IssueCode.WRONG_YEAR,),
        allow_official_cuet_replica=False,
        allow_official_clat_replica=False,
    )