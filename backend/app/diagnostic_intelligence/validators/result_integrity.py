from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DiagnosticIssueCode


def validate_result_integrity(
    request: DiagnosticAuthoringRequest,
    result: DistractorDiagnosticResult,
) -> list[str]:
    issues: list[str] = []
    item = request.item
    if result.item_id != item.item_id:
        issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
        issues.append("result_item_id_mismatch")
    if result.question_type != item.question_type:
        issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
        issues.append("result_question_type_mismatch")

    canonical_keys = {o.option_key for o in item.options}
    canonical_correct = {o.option_key: o.is_correct for o in item.options}
    seen: set[str] = set()
    for tag in result.option_tags:
        if tag.option_key in seen:
            issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
            issues.append("duplicate_option_tag_key")
        seen.add(tag.option_key)
        if tag.option_key not in canonical_keys:
            issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
            issues.append("unknown_option_tag_key")
        elif tag.is_correct != canonical_correct[tag.option_key]:
            if canonical_correct[tag.option_key]:
                issues.append(DiagnosticIssueCode.CORRECT_OPTION_MISLABELED.value)
            else:
                issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
                issues.append("option_correctness_mismatch")

    missing = canonical_keys - seen
    extra = seen - canonical_keys
    if missing:
        issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
        issues.append("missing_option_tags")
    if extra:
        issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
        issues.append("extra_option_tags")
    if not result.option_tags and canonical_keys:
        issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
        issues.append("empty_option_tags")
    return issues


def canonical_option_text(request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag) -> str:
    for option in request.item.options:
        if option.option_key == tag.option_key:
            return option.text
    return ""
