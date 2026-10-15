from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.integration.revision_tenancy import tenant_scope_mismatch


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
    if result.taxonomy_version != request.taxonomy_version:
        issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
        issues.append("result_taxonomy_version_mismatch")

    canonical_item_sources = set(item.source_revision_ids)
    if result.source_revision_ids:
        if set(result.source_revision_ids) != canonical_item_sources:
            issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
            issues.append("result_source_revision_mismatch")
        for revision_id in result.source_revision_ids:
            record = request.revision_tenant_records.get(revision_id)
            if record is not None and tenant_scope_mismatch(
                organization_id=request.organization_id,
                institution_id=request.institution_id,
                teacher_id=request.teacher_id,
                record=record,
            ):
                issues.append(DiagnosticIssueCode.TENANT_EVIDENCE_MISMATCH.value)

    canonical_keys = {o.option_key for o in item.options}
    canonical_correct = {o.option_key: o.is_correct for o in item.options}
    seen: set[str] = set()
    for tag in result.option_tags:
        if tag.item_id != item.item_id:
            issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
            issues.append("tag_item_id_mismatch")
        if tag.taxonomy_version != request.taxonomy_version:
            issues.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
            issues.append("tag_taxonomy_version_mismatch")
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


def canonical_text_by_option_key(request: DiagnosticAuthoringRequest) -> dict[str, str]:
    return {option.option_key: option.text for option in request.item.options}
