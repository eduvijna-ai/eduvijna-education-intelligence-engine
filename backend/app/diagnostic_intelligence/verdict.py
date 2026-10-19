from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticVerdict,
    DiagnosticVerdictItem,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DiagnosticIssueCode, DiagnosticValidationStatus

_BLOCKING_CODES = {
    "unknown_misconception_code",
    "inactive_misconception",
    "curriculum_scope_mismatch",
    "correct_option_mislabeled",
    "forged_evidence_ref",
    "unbound_diagnostic_evidence",
    "tenant_evidence_mismatch",
    "taxonomy_evidence_ungrounded",
    "day6_blocking",
    "nonsensical_distractor",
    "non_candidate_misconception",
    "missing_diagnostic_evidence",
    DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value,
    "empty_option_tags",
    "missing_option_tags",
    "extra_option_tags",
    "duplicate_option_tag_key",
    "unknown_option_tag_key",
    "option_correctness_mismatch",
    "result_item_id_mismatch",
    "result_question_type_mismatch",
    "unauthorized_source_revision",
    "result_source_revision_mismatch",
}

_REPAIRABLE_CODES = {
    "duplicate_misconception",
    "redundant_distractor",
    "signal_text_mismatch",
    "missing_diagnostic_tag",
    "second_correct_distractor",
}

_REVIEW_ONLY_CODES = {
    "factual_unverified",
    "no_misconception_candidates",
    "plausibility_unverified",
    "insufficient_diagnostic_grounding",
}


def propagate_item_level_option_issues(
    option_issues: dict[str, list[str]],
    item_level_issues: list[str],
    *,
    wrong_option_keys: list[str],
) -> dict[str, list[str]]:
    propagated = {key: list(codes) for key, codes in option_issues.items()}
    for code in item_level_issues:
        if code not in (
            {"duplicate_misconception", "redundant_distractor"}
            | _BLOCKING_CODES
            | _REVIEW_ONLY_CODES
        ):
            continue
        for key in wrong_option_keys:
            bucket = propagated.setdefault(key, [])
            if code not in bucket:
                bucket.append(code)
    return propagated


def status_for_issue_codes(codes: list[str]) -> DiagnosticValidationStatus:
    if not codes:
        return DiagnosticValidationStatus.PASS
    if any(code in _BLOCKING_CODES for code in codes):
        return DiagnosticValidationStatus.REJECT
    if any(code in _REVIEW_ONLY_CODES for code in codes):
        return DiagnosticValidationStatus.REVIEW_REQUIRED
    if any(code in _REPAIRABLE_CODES for code in codes):
        return DiagnosticValidationStatus.REPAIR
    return DiagnosticValidationStatus.REJECT


def build_diagnostic_verdict(
    item_id: str,
    option_issues: dict[str, list[str]],
    item_level_issues: list[str],
    *,
    repairable_codes: set[str] | None = None,
    tags_by_key: dict[str, OptionDiagnosticTag] | None = None,
    wrong_option_keys: list[str] | None = None,
) -> DiagnosticVerdict:
    repairable_codes = repairable_codes or _REPAIRABLE_CODES
    wrong_keys = wrong_option_keys or [
        key for key, tag in (tags_by_key or {}).items() if not tag.is_correct
    ]
    option_issues = propagate_item_level_option_issues(
        option_issues, item_level_issues, wrong_option_keys=wrong_keys
    )

    items: list[DiagnosticVerdictItem] = []
    all_codes: list[str] = list(item_level_issues)
    option_keys = sorted(
        set(option_issues.keys()) | set((tags_by_key or {}).keys()),
    )
    for option_key in option_keys:
        codes = option_issues.get(option_key, [])
        all_codes.extend(codes)
        status = status_for_issue_codes(codes)
        repair_instructions: list[str] = []
        if codes and status == DiagnosticValidationStatus.REPAIR:
            repair_instructions.append(
                f"Repair diagnostic tags for option {option_key}: {','.join(codes)}"
            )
        tag = (tags_by_key or {}).get(option_key)
        field_paths: list[str] = []
        misconception_code = None
        evidence_refs: list[str] = []
        if tag is not None:
            misconception_code = tag.misconception_code
            evidence_refs = list(tag.evidence_refs)
            field_paths.append(f"option_tags.{option_key}")
            if misconception_code and not tag.is_correct:
                field_paths.append(f"option_tags.{option_key}.misconception_code")
            if not tag.is_correct:
                field_paths.append(f"option_tags.{option_key}.evidence_refs")
        items.append(
            DiagnosticVerdictItem(
                item_id=item_id,
                option_key=option_key,
                status=status,
                issue_codes=codes,
                field_paths=field_paths,
                misconception_code=misconception_code,
                evidence_refs=evidence_refs,
                repair_instructions=repair_instructions,
            )
        )

    blocking = any(code in _BLOCKING_CODES for code in all_codes)
    repairable = any(code in repairable_codes for code in all_codes) and not blocking
    review_required = any(code in _REVIEW_ONLY_CODES for code in all_codes)
    if review_required:
        repairable = False
    elif all_codes and not blocking and not repairable:
        review_required = True

    if not all_codes:
        aggregate = DiagnosticValidationStatus.PASS
    elif blocking:
        aggregate = DiagnosticValidationStatus.REJECT
    elif repairable:
        aggregate = DiagnosticValidationStatus.REPAIR
    elif review_required:
        aggregate = DiagnosticValidationStatus.REVIEW_REQUIRED
    else:
        aggregate = DiagnosticValidationStatus.REJECT

    if item_level_issues:
        items.append(
            DiagnosticVerdictItem(
                item_id=item_id,
                option_key=None,
                status=aggregate,
                issue_codes=list(item_level_issues),
                field_paths=["item.diagnostic_integrity"],
                repair_instructions=[],
            )
        )

    repair_instructions = []
    for entry in items:
        repair_instructions.extend(entry.repair_instructions)
    return DiagnosticVerdict(
        item_id=item_id,
        status=aggregate,
        items=items,
        issue_codes=sorted(set(all_codes)),
        repair_instructions=repair_instructions,
        blocking=blocking,
        repairable=repairable,
        review_required=review_required,
    )
