from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.evidence_policy import tag_requires_approved_evidence
from app.diagnostic_intelligence.integration.revision_tenancy import (
    looks_like_revision_id,
    normalize_revision_ref,
    tenant_scope_mismatch,
)
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def _citation_revision_map(request: DiagnosticAuthoringRequest) -> dict[str, str]:
    if request.trusted_citation_revision_map:
        return dict(request.trusted_citation_revision_map)
    if not [s for s in request.item.source_revision_ids if str(s).strip()]:
        return {
            snippet.citation_label: snippet.source_revision_id
            for snippet in request.day7_evidence_snippets
        }
    return {}


def _ref_to_revision_id(request: DiagnosticAuthoringRequest, ref: str) -> str | None:
    citations = _citation_revision_map(request)
    if ref in citations:
        return citations[ref]
    normalized = normalize_revision_ref(ref)
    allowed = request.allowed_source_revision_ids
    if normalized in allowed or ref in allowed:
        return normalized or ref
    return normalized if normalized else None


def validate_evidence_refs(
    request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag
) -> list[str]:
    if tag.is_correct:
        return []
    issues: list[str] = []
    if tag_requires_approved_evidence(request, tag) and not tag.evidence_refs:
        issues.append(DiagnosticIssueCode.MISSING_DIAGNOSTIC_EVIDENCE.value)
        return issues
    allowed_refs = set(request.allowed_evidence_refs)
    allowed_revisions = set(request.allowed_source_revision_ids)
    resolved_revisions: list[str] = []
    for ref in tag.evidence_refs:
        if ref in allowed_refs:
            revision_id = _ref_to_revision_id(request, ref)
            if revision_id:
                resolved_revisions.append(revision_id)
            elif request.trusted_citation_revision_map:
                issues.append(DiagnosticIssueCode.FORGED_EVIDENCE_REF.value)
                continue
            continue
        revision_id = normalize_revision_ref(ref)
        if revision_id in allowed_revisions or ref in allowed_revisions:
            resolved_revisions.append(revision_id or ref)
            continue
        record = request.revision_tenant_records.get(revision_id)
        if record is not None:
            if tenant_scope_mismatch(
                organization_id=request.organization_id,
                institution_id=request.institution_id,
                teacher_id=request.teacher_id,
                record=record,
            ):
                issues.append(DiagnosticIssueCode.TENANT_EVIDENCE_MISMATCH.value)
            else:
                issues.append(DiagnosticIssueCode.FORGED_EVIDENCE_REF.value)
            continue
        if looks_like_revision_id(ref):
            issues.append(DiagnosticIssueCode.FORGED_EVIDENCE_REF.value)
        else:
            issues.append(DiagnosticIssueCode.FORGED_EVIDENCE_REF.value)

    if issues:
        return issues

    if not tag.misconception_code:
        return issues

    definition = resolve_misconception(
        tag.misconception_code, taxonomy_version=request.taxonomy_version
    )
    if definition is None or not definition.evidence_source_revision_ids:
        return issues

    required = set(definition.evidence_source_revision_ids)
    if not tag.evidence_refs:
        return issues

    grounded = any(rev in required for rev in resolved_revisions)
    if not grounded:
        issues.append(DiagnosticIssueCode.TAXONOMY_EVIDENCE_UNGROUNDED.value)
    return issues
