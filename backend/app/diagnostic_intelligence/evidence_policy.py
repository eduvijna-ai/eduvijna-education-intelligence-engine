"""Source-backed vs synthetic diagnostic evidence policy (D9-07)."""

from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def item_claims_source_provenance(request: DiagnosticAuthoringRequest) -> bool:
    """Trusted canonical source claims only — never model draft metadata."""
    return bool(request.item.source_revision_ids)


def tag_requires_approved_evidence(
    request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag
) -> bool:
    if tag.is_correct or not tag.misconception_code:
        return False
    definition = resolve_misconception(
        tag.misconception_code, taxonomy_version=request.taxonomy_version
    )
    if definition is not None and definition.evidence_source_revision_ids:
        return True
    return item_claims_source_provenance(request)
