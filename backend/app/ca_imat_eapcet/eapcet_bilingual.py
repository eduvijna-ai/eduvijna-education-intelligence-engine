from __future__ import annotations

from app.ca_imat_eapcet.enums import IssueCode

_SUPPORTED_PAIRS = frozenset({"english_telugu", "english_urdu", "english_only"})


def validate_bilingual_medium(medium_pair: str) -> list[IssueCode]:
    """D14-24: typed failure for unsupported translation policies."""

    if medium_pair not in _SUPPORTED_PAIRS:
        return [IssueCode.EAPCET_BILINGUAL_MISMATCH]
    return []


def semantic_equivalence_check(english: str, vernacular: str) -> list[IssueCode]:
    """Synthetic stub: real attestation requires source-approved bilingual keys."""

    if not english.strip() or not vernacular.strip():
        return [IssueCode.EAPCET_BILINGUAL_MISMATCH]
    return []