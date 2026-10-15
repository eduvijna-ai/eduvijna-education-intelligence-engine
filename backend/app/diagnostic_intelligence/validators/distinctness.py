from __future__ import annotations

from collections import Counter

from app.diagnostic_intelligence.contracts import DiagnosticCoverageSummary, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode


def validate_distinctness(
    item_id: str,
    tags: list[OptionDiagnosticTag],
    *,
    canonical_text_by_key: dict[str, str] | None = None,
) -> tuple[list[str], DiagnosticCoverageSummary]:
    wrong_tags = [t for t in tags if not t.is_correct and t.misconception_code]
    codes = [t.misconception_code for t in wrong_tags if t.misconception_code]
    counts = Counter(codes)
    duplicate_codes = [code for code, count in counts.items() if count > 1]
    issues: list[str] = []
    if duplicate_codes:
        issues.append(DiagnosticIssueCode.DUPLICATE_MISCONCEPTION.value)
    canonical_map = canonical_text_by_key or {}
    normalized: list[str] = []
    for tag in wrong_tags:
        text = canonical_map.get(tag.option_key, "")
        if not text:
            text = str(tag.metadata_json.get("option_text") or "")
        normalized.append(str(text).strip().lower())
    normalized = [value for value in normalized if value]
    if len(normalized) != len(set(normalized)):
        issues.append(DiagnosticIssueCode.REDUNDANT_DISTRACTOR.value)
    missing = sum(1 for t in tags if not t.is_correct and not t.misconception_code)
    summary = DiagnosticCoverageSummary(
        item_id=item_id,
        distinct_misconception_codes=sorted(set(codes)),
        duplicate_codes=duplicate_codes,
        missing_distractor_tags=missing,
        coverage_complete=missing == 0 and not duplicate_codes,
    )
    return issues, summary
