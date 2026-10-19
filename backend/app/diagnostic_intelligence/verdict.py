from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticVerdict,
    DiagnosticVerdictItem,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DiagnosticIssueCode, DiagnosticValidationStatus


def build_diagnostic_verdict(
    item_id: str,
    option_issues: dict[str, list[str]],
    item_level_issues: list[str],
    *,
    repairable_codes: set[str] | None = None,
    tags_by_key: dict[str, OptionDiagnosticTag] | None = None,
) -> DiagnosticVerdict:
    repairable_codes = repairable_codes or {
        "duplicate_misconception",
        "redundant_distractor",
        "signal_text_mismatch",
        "missing_diagnostic_tag",
        "second_correct_distractor",
    }
    items: list[DiagnosticVerdictItem] = []
    all_codes: list[str] = list(item_level_issues)
    for option_key, codes in option_issues.items():
        all_codes.extend(codes)
        status = DiagnosticValidationStatus.PASS
        repair_instructions: list[str] = []
        if codes:
            if any(c in repairable_codes for c in codes):
                status = DiagnosticValidationStatus.REPAIR
                repair_instructions.append(
                    f"Repair diagnostic tags for option {option_key}: {','.join(codes)}"
                )
            else:
                status = DiagnosticValidationStatus.REJECT
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
            if evidence_refs and not tag.is_correct:
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
    blocking = any(
        code
        in {
            "unknown_misconception_code",
            "inactive_misconception",
            "curriculum_scope_mismatch",
            "correct_option_mislabeled",
            "forged_evidence_ref",
            "tenant_evidence_mismatch",
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
        }
        for code in all_codes
    )
    repairable = any(code in repairable_codes for code in all_codes) and not blocking
    review_only = {
        "factual_unverified",
        "no_misconception_candidates",
        "plausibility_unverified",
        "insufficient_diagnostic_grounding",
    }
    if any(code in review_only for code in all_codes):
        review_required = True
        repairable = False
    else:
        review_required = bool(all_codes) and not blocking and not repairable
    if not all_codes:
        aggregate = DiagnosticValidationStatus.PASS
    elif blocking:
        aggregate = DiagnosticValidationStatus.REJECT
    elif repairable:
        aggregate = DiagnosticValidationStatus.REPAIR
    elif review_required:
        aggregate = DiagnosticValidationStatus.REVIEW_REQUIRED
    else:
        aggregate = DiagnosticValidationStatus.REVIEW_REQUIRED
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
