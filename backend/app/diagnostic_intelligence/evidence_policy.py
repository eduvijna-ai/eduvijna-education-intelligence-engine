"""Source-backed vs synthetic diagnostic evidence policy (D9-07)."""

from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def is_synthetic_taxonomy_only(request: DiagnosticAuthoringRequest) -> bool:
    if request.synthetic_taxonomy_only:
        return True
    if request.item.metadata_json.get("synthetic_fixture"):
        return True
    if not request.item.source_revision_ids:
        return True
    return False


def tag_requires_approved_evidence(
    request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag
) -> bool:
    if tag.is_correct or not tag.misconception_code:
        return False
    if is_synthetic_taxonomy_only(request):
        return False
    definition = resolve_misconception(
        tag.misconception_code, taxonomy_version=request.taxonomy_version
    )
    if definition is None:
        return bool(request.item.source_revision_ids)
    if definition.evidence_source_revision_ids:
        return True
    return bool(request.item.source_revision_ids)
