from __future__ import annotations

from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict


def validate_whole_paper(
    *,
    questions: list[QuestionRef],
    expected_count: int,
    expected_sections: dict[str, int] | None = None,
) -> tuple[PlanVerdict, list[IssueCode]]:
    """D14-31: cardinality, duplicates, section rules."""

    issues: list[IssueCode] = []
    if len(questions) != expected_count:
        issues.append(IssueCode.IMAT_COUNT_MISMATCH)
    fps = [q.fingerprint for q in questions]
    if len(set(fps)) != len(fps):
        issues.append(IssueCode.DUPLICATE_QUESTION)

    if expected_sections:
        actual: dict[str, int] = {}
        for q in questions:
            actual[q.paper_or_section] = actual.get(q.paper_or_section, 0) + 1
        for section, need in expected_sections.items():
            if actual.get(section, 0) != need:
                issues.append(IssueCode.EAPCET_COUNT_MISMATCH)

    if issues:
        return PlanVerdict.FAIL, issues
    return PlanVerdict.PASS, []