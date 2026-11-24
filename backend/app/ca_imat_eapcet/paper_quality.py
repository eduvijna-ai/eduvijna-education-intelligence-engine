from __future__ import annotations

from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED
from app.ca_imat_eapcet.content_validation import derive_content_fingerprint
from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict
from app.ca_imat_eapcet.semantic_dedup import semantic_stem_key


def validate_whole_paper(
    *,
    questions: list[QuestionRef],
    expected_count: int,
    expected_sections: dict[str, int] | None = None,
    allowed_sections: frozenset[str] | None = None,
) -> tuple[PlanVerdict, list[IssueCode]]:
    if ACADEMIC_VALIDATION_DISABLED:
        return PlanVerdict.NOT_READY, [IssueCode.ACADEMIC_VALIDATION_CONTAINED]
    issues: list[IssueCode] = []
    if len(questions) != expected_count:
        issues.append(IssueCode.IMAT_COUNT_MISMATCH)

    fps = [q.fingerprint for q in questions]
    sem = [semantic_stem_key(q.stem_text or "") for q in questions]
    if len(set(fps)) != len(fps) or len(set(sem)) != len(sem):
        issues.append(IssueCode.DUPLICATE_QUESTION)

    for q in questions:
        if not q.stem_text or not q.options:
            issues.append(IssueCode.VALIDATION_NOT_PROVEN)
        expected_fp = derive_content_fingerprint(
            stem_text=q.stem_text or "",
            options=q.options,
            correct_key=q.correct_key,
        )
        if q.fingerprint != expected_fp:
            issues.append(IssueCode.FINGERPRINT_TAMPER)
        if not q.independently_validated:
            issues.append(IssueCode.VALIDATION_NOT_PROVEN)

    if expected_sections:
        actual: dict[str, int] = {}
        for q in questions:
            actual[q.paper_or_section] = actual.get(q.paper_or_section, 0) + 1
        for section, need in expected_sections.items():
            if actual.get(section, 0) != need:
                issues.append(IssueCode.EAPCET_COUNT_MISMATCH)

    if allowed_sections:
        for q in questions:
            if q.paper_or_section not in allowed_sections:
                issues.append(IssueCode.WRONG_STREAM)

    if issues:
        return PlanVerdict.FAIL, list(dict.fromkeys(issues))
    return PlanVerdict.PASS, []