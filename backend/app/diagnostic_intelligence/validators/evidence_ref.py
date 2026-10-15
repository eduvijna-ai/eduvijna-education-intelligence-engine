from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.integration.revision_tenancy import (
    looks_like_revision_id,
    normalize_revision_ref,
    tenant_scope_mismatch,
)


def validate_evidence_refs(
    request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag
) -> list[str]:
    if tag.is_correct:
        return []
    issues: list[str] = []
    allowed_refs = set(request.allowed_evidence_refs)
    allowed_revisions = set(request.allowed_source_revision_ids)
    for ref in tag.evidence_refs:
        if ref in allowed_refs:
            continue
        revision_id = normalize_revision_ref(ref)
        if revision_id in allowed_revisions or ref in allowed_revisions:
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
    return issues
