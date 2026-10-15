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
    for ref in tag.evidence_refs:
        if ref in allowed_refs:
            continue
        if ref in allowed_revisions:
            continue
        if ref.startswith("rev:") and ref[4:] in allowed_revisions:
            continue
        if _looks_like_revision_id(ref) and ref not in allowed_revisions:
            issues.append(DiagnosticIssueCode.TENANT_EVIDENCE_MISMATCH.value)
            continue
        issues.append(DiagnosticIssueCode.FORGED_EVIDENCE_REF.value)
    return issues


def _looks_like_revision_id(value: str) -> bool:
    parts = value.split("-")
    return len(parts) == 5 and len(value) >= 32
