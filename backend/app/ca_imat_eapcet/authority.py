from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    IssueCode,
    PlanVerdict,
)
from app.ca_imat_eapcet.source_registry import (
    ca_icai_evidence_ready,
    eapcet_official_evidence_ready,
    imat_decree_evidence_ready,
)


@dataclass(frozen=True, slots=True)
class ProfileAuthorityDecision:
    trust_mode: Day14SourceTrustMode
    verdict: PlanVerdict | None
    issue_codes: tuple[IssueCode, ...]
    allow_official_ca_replica: bool
    allow_official_imat_replica: bool
    allow_official_eapcet_replica: bool


def resolve_ca_authority(
    *,
    profile_kind: Day14ProfileKind,
    session_code: str,
    session: Session | None = None,
) -> ProfileAuthorityDecision:
    """D14-04: CA Foundation session isolation; future sessions fail closed."""

    if profile_kind is Day14ProfileKind.SYNTHETIC_DEMO:
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            verdict=None,
            issue_codes=(),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    if profile_kind is Day14ProfileKind.CA_FUTURE_SESSION or session_code.startswith("future"):
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.CA_FUTURE_UNVERIFIED,
            verdict=PlanVerdict.OFFICIAL_NOT_VERIFIED,
            issue_codes=(IssueCode.CA_FUTURE_SESSION, IssueCode.UNAPPROVED_SOURCE),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    if profile_kind is Day14ProfileKind.CA_SESSION_JAN2027:
        if not ca_icai_evidence_ready(session):
            return ProfileAuthorityDecision(
                trust_mode=Day14SourceTrustMode.CA_ICAI_REFERENCE,
                verdict=PlanVerdict.SOURCE_PENDING,
                issue_codes=(IssueCode.UNAPPROVED_SOURCE,),
                allow_official_ca_replica=False,
                allow_official_imat_replica=False,
                allow_official_eapcet_replica=False,
            )
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.CA_ICAI_REFERENCE,
            verdict=None,
            issue_codes=(),
            allow_official_ca_replica=True,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    return ProfileAuthorityDecision(
        trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
        verdict=PlanVerdict.REVIEW_REQUIRED,
        issue_codes=(IssueCode.WRONG_YEAR,),
        allow_official_ca_replica=False,
        allow_official_imat_replica=False,
        allow_official_eapcet_replica=False,
    )


def resolve_imat_authority(
    *,
    profile_kind: Day14ProfileKind,
    academic_year: str,
    session: Session | None = None,
) -> ProfileAuthorityDecision:
    """D14-16/20: IMAT annual decree binding; unsupported future years vetoed."""

    if profile_kind is Day14ProfileKind.SYNTHETIC_DEMO:
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            verdict=None,
            issue_codes=(),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    if profile_kind is Day14ProfileKind.IMAT_FUTURE_YEAR or academic_year not in {"2026", "2027"}:
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.IMAT_FUTURE_UNVERIFIED,
            verdict=PlanVerdict.OFFICIAL_NOT_VERIFIED,
            issue_codes=(IssueCode.IMAT_FUTURE_YEAR, IssueCode.UNAPPROVED_SOURCE),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    if profile_kind is Day14ProfileKind.IMAT_2026:
        if not imat_decree_evidence_ready(session):
            return ProfileAuthorityDecision(
                trust_mode=Day14SourceTrustMode.IMAT_DM1005_2026,
                verdict=PlanVerdict.SOURCE_PENDING,
                issue_codes=(IssueCode.UNAPPROVED_SOURCE,),
                allow_official_ca_replica=False,
                allow_official_imat_replica=False,
                allow_official_eapcet_replica=False,
            )
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.IMAT_DM1005_2026,
            verdict=None,
            issue_codes=(),
            allow_official_ca_replica=False,
            allow_official_imat_replica=True,
            allow_official_eapcet_replica=False,
        )

    return ProfileAuthorityDecision(
        trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
        verdict=PlanVerdict.REVIEW_REQUIRED,
        issue_codes=(IssueCode.WRONG_YEAR,),
        allow_official_ca_replica=False,
        allow_official_imat_replica=False,
        allow_official_eapcet_replica=False,
    )


def resolve_eapcet_authority(
    *,
    profile_kind: Day14ProfileKind,
    stream: EapcetStream,
    exam_year: str,
    session: Session | None = None,
) -> ProfileAuthorityDecision:
    """D14-21: EAPCET stream/version isolation; discovery mirror never activates official."""

    if profile_kind is Day14ProfileKind.SYNTHETIC_DEMO:
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            verdict=None,
            issue_codes=(),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    if exam_year != "2026":
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.EAPCET_DISCOVERY_MIRROR_ONLY,
            verdict=PlanVerdict.OFFICIAL_NOT_VERIFIED,
            issue_codes=(IssueCode.WRONG_YEAR, IssueCode.UNAPPROVED_SOURCE),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    if not eapcet_official_evidence_ready(session):
        return ProfileAuthorityDecision(
            trust_mode=Day14SourceTrustMode.EAPCET_OFFICIAL_2026,
            verdict=PlanVerdict.SOURCE_PENDING,
            issue_codes=(IssueCode.EAPCET_OFFICIAL_UNATTESTED, IssueCode.UNAPPROVED_SOURCE),
            allow_official_ca_replica=False,
            allow_official_imat_replica=False,
            allow_official_eapcet_replica=False,
        )

    _ = stream
    return ProfileAuthorityDecision(
        trust_mode=Day14SourceTrustMode.EAPCET_OFFICIAL_2026,
        verdict=None,
        issue_codes=(),
        allow_official_ca_replica=False,
        allow_official_imat_replica=False,
        allow_official_eapcet_replica=True,
    )