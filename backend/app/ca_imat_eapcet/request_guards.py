from __future__ import annotations

from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    EAPCET_PACK_CODE,
    IMAT_PACK_CODE,
    MAX_ALLOCATE_COUNT,
)
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    IssueCode,
)

_PROFILE_TRUST: dict[tuple[str, Day14ProfileKind], frozenset[Day14SourceTrustMode]] = {
    (CA_FOUNDATION_PACK_CODE, Day14ProfileKind.SYNTHETIC_DEMO): frozenset(
        {Day14SourceTrustMode.SYNTHETIC_FIXTURE}
    ),
    (IMAT_PACK_CODE, Day14ProfileKind.SYNTHETIC_DEMO): frozenset(
        {Day14SourceTrustMode.SYNTHETIC_FIXTURE}
    ),
    (EAPCET_PACK_CODE, Day14ProfileKind.SYNTHETIC_DEMO): frozenset(
        {Day14SourceTrustMode.SYNTHETIC_FIXTURE}
    ),
    (CA_FOUNDATION_PACK_CODE, Day14ProfileKind.CA_SESSION_JAN2027): frozenset(
        {Day14SourceTrustMode.CA_ICAI_REFERENCE}
    ),
    (IMAT_PACK_CODE, Day14ProfileKind.IMAT_2026): frozenset(
        {Day14SourceTrustMode.IMAT_DM1005_2026}
    ),
    (EAPCET_PACK_CODE, Day14ProfileKind.EAPCET_ENGINEERING_2026): frozenset(
        {Day14SourceTrustMode.EAPCET_OFFICIAL_2026}
    ),
}


def validate_requested_count(count: int) -> list[IssueCode]:
    if not isinstance(count, int) or count < 1 or count > MAX_ALLOCATE_COUNT:
        return [IssueCode.INVALID_REQUEST_COUNT]
    return []


def validate_profile_trust_matrix(
    *,
    exam_pack_code: str,
    profile_kind: Day14ProfileKind,
    trust_mode: Day14SourceTrustMode,
) -> list[IssueCode]:
    allowed = _PROFILE_TRUST.get((exam_pack_code, profile_kind))
    if allowed is None:
        return [IssueCode.UNAPPROVED_SOURCE]
    if trust_mode not in allowed:
        return [IssueCode.UNAPPROVED_SOURCE]
    return []


def validate_organization_required(
    *,
    profile_kind: Day14ProfileKind,
    organization_id: str | None,
) -> list[IssueCode]:
    if profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO and not organization_id:
        return [IssueCode.MISSING_TENANT_CONTEXT]
    return []