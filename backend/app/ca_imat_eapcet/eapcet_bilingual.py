from __future__ import annotations

from dataclasses import dataclass

from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict

_SUPPORTED_PAIRS = frozenset({"english_telugu", "english_urdu", "english_only"})


@dataclass(frozen=True, slots=True)
class BilingualVerdict:
    verdict: PlanVerdict
    issue_codes: tuple[IssueCode, ...]


def validate_bilingual_medium(medium_pair: str) -> list[IssueCode]:
    if medium_pair not in _SUPPORTED_PAIRS:
        return [IssueCode.EAPCET_BILINGUAL_MISMATCH]
    return []


def evaluate_bilingual_pair(
    medium_pair: str,
    *,
    english: str | None = None,
    vernacular: str | None = None,
    equivalence_evidence_id: str | None = None,
) -> BilingualVerdict:
    """D14-24: unsupported or unproven translation never passes."""

    issues = validate_bilingual_medium(medium_pair)
    if issues:
        return BilingualVerdict(verdict=PlanVerdict.REVIEW_REQUIRED, issue_codes=tuple(issues))

    if medium_pair == "english_only":
        if english and english.strip():
            return BilingualVerdict(verdict=PlanVerdict.PASS, issue_codes=())
        return BilingualVerdict(
            verdict=PlanVerdict.REVIEW_REQUIRED,
            issue_codes=(IssueCode.EAPCET_BILINGUAL_MISMATCH,),
        )

    if not english or not vernacular or not english.strip() or not vernacular.strip():
        return BilingualVerdict(
            verdict=PlanVerdict.REVIEW_REQUIRED,
            issue_codes=(IssueCode.EAPCET_BILINGUAL_MISMATCH,),
        )
    if not equivalence_evidence_id:
        return BilingualVerdict(
            verdict=PlanVerdict.REVIEW_REQUIRED,
            issue_codes=(IssueCode.EAPCET_BILINGUAL_MISMATCH,),
        )
    return BilingualVerdict(verdict=PlanVerdict.PASS, issue_codes=())