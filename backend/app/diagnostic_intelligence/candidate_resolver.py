from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    MisconceptionDefinition,
)
from app.diagnostic_intelligence.enums import MisconceptionStatus
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy


def resolve_misconception_candidates(
    request: DiagnosticAuthoringRequest,
) -> list[MisconceptionDefinition]:
    taxonomy = load_taxonomy(request.taxonomy_version)
    candidates: list[MisconceptionDefinition] = []
    for entry in taxonomy.misconceptions:
        if entry.status != MisconceptionStatus.ACTIVE:
            continue
        if (
            request.subject_code
            and entry.subject_code
            and entry.subject_code != request.subject_code
        ):
            continue
        if request.grade_year_code and entry.grade_year_code:
            if entry.grade_year_code != request.grade_year_code:
                continue
        if request.topic_codes and entry.topic_codes:
            if not set(request.topic_codes).intersection(entry.topic_codes):
                continue
        if request.concept_codes and entry.concept_codes:
            if not set(request.concept_codes).intersection(entry.concept_codes):
                continue
        if request.learning_outcome_ids and entry.learning_outcome_ids:
            if not set(request.learning_outcome_ids).intersection(entry.learning_outcome_ids):
                continue
        candidates.append(entry)
    return candidates
