from __future__ import annotations

TAG_ONLY_DIAGNOSTIC_ISSUES = frozenset(
    {
        "signal_text_mismatch",
        "duplicate_misconception",
        "redundant_distractor",
        "missing_diagnostic_tag",
        "forged_evidence_ref",
        "unknown_misconception_code",
        "inactive_misconception",
        "curriculum_scope_mismatch",
        "non_candidate_misconception",
    }
)

AUTHOR_REQUIRED_ISSUES = frozenset(
    {
        "second_correct_distractor",
        "nonsensical_distractor",
        "correct_option_mislabeled",
        "day6_blocking",
    }
)


def diagnostic_repair_is_tag_only(issue_codes: list[str]) -> bool:
    if not issue_codes:
        return False
    if any(code in AUTHOR_REQUIRED_ISSUES for code in issue_codes):
        return False
    return all(code in TAG_ONLY_DIAGNOSTIC_ISSUES for code in issue_codes)
