from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode


def validate_evidence_refs(
    request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag
) -> list[str]:
    if tag.is_correct:
        return []
    issues: list[str] = []
    allowed_refs = set(request.allowed_evidence_refs)
    allowed_revisions = set(request.allowed_source_revision_ids)
    blocked_tenant = set(request.blocked_tenant_revision_ids)
    for ref in tag.evidence_refs:
        if ref in allowed_refs:
            continue
        if ref in allowed_revisions:
            continue
        if ref.startswith("rev:") and ref[4:] in allowed_revisions:
            continue
        if ref in blocked_tenant:
            issues.append(DiagnosticIssueCode.TENANT_EVIDENCE_MISMATCH.value)
            continue
        if ref in allowed_revisions or ref.removeprefix("rev:") in allowed_revisions:
            continue
        issues.append(DiagnosticIssueCode.FORGED_EVIDENCE_REF.value)
    return issues
