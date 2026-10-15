from __future__ import annotations

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode


def correct_option_integrity_issues(tags: list[OptionDiagnosticTag]) -> list[str]:
    issues: list[str] = []
    for tag in tags:
        if not tag.is_correct:
            continue
        if tag.misconception_code:
            issues.append(DiagnosticIssueCode.CORRECT_OPTION_MISLABELED.value)
        if tag.diagnostic_signal and tag.diagnostic_signal not in {"", "none", "correct"}:
            issues.append(DiagnosticIssueCode.CORRECT_OPTION_MISLABELED.value)
    return issues
