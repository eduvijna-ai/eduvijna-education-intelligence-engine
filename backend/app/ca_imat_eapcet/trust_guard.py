from __future__ import annotations

from app.ca_imat_eapcet.enums import Day14ProfileKind, Day14SourceTrustMode, IssueCode

_SYNTHETIC_PROFILES = frozenset({Day14ProfileKind.SYNTHETIC_DEMO})
_SYNTHETIC_TRUST = Day14SourceTrustMode.SYNTHETIC_FIXTURE


def validate_trust_coherence(
    *,
    profile_kind: Day14ProfileKind,
    trust_mode: Day14SourceTrustMode,
    exam_family: str,
) -> list[IssueCode]:
    """Reject official trust modes on synthetic profiles and vice versa."""

    issues: list[IssueCode] = []
    if profile_kind in _SYNTHETIC_PROFILES and trust_mode is not _SYNTHETIC_TRUST:
        issues.append(IssueCode.UNAPPROVED_SOURCE)
    if trust_mode is _SYNTHETIC_TRUST and profile_kind not in _SYNTHETIC_PROFILES:
        issues.append(IssueCode.UNAPPROVED_SOURCE)
    if trust_mode is Day14SourceTrustMode.EAPCET_DISCOVERY_MIRROR_ONLY:
        issues.append(IssueCode.DISCOVERY_MIRROR_ONLY)
    _ = exam_family
    return issues