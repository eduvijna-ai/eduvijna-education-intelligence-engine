from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    MisconceptionDefinition,
)
from app.diagnostic_intelligence.enums import MisconceptionStatus
from app.diagnostic_intelligence.scope_policy import definition_matches_request_scope
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy


def resolve_misconception_candidates(
    request: DiagnosticAuthoringRequest,
) -> list[MisconceptionDefinition]:
    taxonomy = load_taxonomy(request.taxonomy_version)
    candidates: list[MisconceptionDefinition] = []
    for entry in taxonomy.misconceptions:
        if entry.status != MisconceptionStatus.ACTIVE:
            continue
        if not definition_matches_request_scope(request, entry):
            continue
        candidates.append(entry)
    return candidates
