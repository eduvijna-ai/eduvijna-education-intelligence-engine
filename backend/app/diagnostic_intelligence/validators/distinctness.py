from __future__ import annotations

import re
from collections import Counter

from app.diagnostic_intelligence.contracts import DiagnosticCoverageSummary, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode


def _meaning_key(text: str) -> str:
    stripped = text.strip().lower()
    match = re.match(r"^(\d+(?:\.\d+)?)", stripped)
    if match:
        raw = match.group(1)
        try:
            value = float(raw)
            if value.is_integer():
                return str(int(value))
            return str(value)
        except ValueError:
            return raw
    return stripped


def validate_distinctness(
    item_id: str,
    tags: list[OptionDiagnosticTag],
    *,
    canonical_text_by_key: dict[str, str] | None = None,
    option_level_issues: dict[str, list[str]] | None = None,
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
    meaning_keys: list[str] = []
    canonical_missing = False
    for tag in wrong_tags:
        text = str(canonical_map.get(tag.option_key, "") or "").strip()
        if not text:
            issues.append("canonical_option_text_missing")
            canonical_missing = True
            continue
        normalized.append(text.lower())
        meaning_keys.append(_meaning_key(text))
    redundant_text = len(normalized) != len(set(normalized))
    redundant_meaning = len(meaning_keys) != len(set(meaning_keys))
    if redundant_text or redundant_meaning:
        issues.append(DiagnosticIssueCode.REDUNDANT_DISTRACTOR.value)
    missing = sum(1 for t in tags if not t.is_correct and not t.misconception_code)
    per_option = option_level_issues or {}
    integrity_blocked = any(
        code
        in {
            "missing_diagnostic_tag",
            DiagnosticIssueCode.MISSING_DIAGNOSTIC_EVIDENCE.value,
            "canonical_option_text_missing",
        }
        for codes in per_option.values()
        for code in codes
    )
    coverage_complete = (
        missing == 0
        and not duplicate_codes
        and not redundant_text
        and not redundant_meaning
        and not canonical_missing
        and not integrity_blocked
        and not issues
    )
    summary = DiagnosticCoverageSummary(
        item_id=item_id,
        distinct_misconception_codes=sorted(set(codes)),
        duplicate_codes=duplicate_codes,
        missing_distractor_tags=missing,
        coverage_complete=coverage_complete,
    )
    return issues, summary
