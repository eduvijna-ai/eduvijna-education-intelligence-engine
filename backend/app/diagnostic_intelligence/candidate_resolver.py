from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    MisconceptionDefinition,
)
from app.diagnostic_intelligence.enums import MisconceptionStatus
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy


def _candidate_filter_aligned(
    request_values: list[str],
    entry_values: list[str],
) -> bool:
    if not request_values:
        return True
    if not entry_values:
        return True
    return bool(set(request_values).intersection(entry_values))


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
        if not _candidate_filter_aligned(request.topic_codes, entry.topic_codes):
            continue
        if not _candidate_filter_aligned(request.concept_codes, entry.concept_codes):
            continue
        if not _candidate_filter_aligned(request.competency_codes, entry.competency_codes):
            continue
        if not _candidate_filter_aligned(
            request.learning_outcome_ids, entry.learning_outcome_ids
        ):
            continue
        candidates.append(entry)
    return candidates
