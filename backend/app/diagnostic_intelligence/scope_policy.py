from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    MisconceptionDefinition,
)

SCOPE_POLICY_VERSION = "misconception-scope-policy@v1"
BROAD_CURRICULUM_SCOPE_KEY = "broad_curriculum_scope"
BROAD_SCOPE_DIMENSIONS_KEY = "broad_scope_dimensions"


def _broad_dimensions(definition: MisconceptionDefinition) -> set[str]:
    if not definition.metadata_json.get(BROAD_CURRICULUM_SCOPE_KEY):
        return set()
    raw = definition.metadata_json.get(BROAD_SCOPE_DIMENSIONS_KEY)
    if isinstance(raw, list) and raw:
        return {str(item) for item in raw}
    return {"learning_outcome_ids"}


def _list_dimension_matches(
    request_values: list[str],
    definition_values: list[str],
    *,
    dimension: str,
    broad_dimensions: set[str],
) -> bool:
    if not request_values:
        return True
    if not definition_values:
        return dimension in broad_dimensions
    return bool(set(request_values).intersection(definition_values))


def _scalar_matches(request_value: str | None, definition_value: str | None) -> bool:
    if not request_value:
        return True
    if not definition_value:
        return False
    return request_value == definition_value


def definition_matches_request_scope(
    request: DiagnosticAuthoringRequest,
    definition: MisconceptionDefinition,
) -> bool:
    broad = _broad_dimensions(definition)
    if not _scalar_matches(request.subject_code, definition.subject_code):
        return False
    if not _scalar_matches(request.grade_year_code, definition.grade_year_code):
        return False
    if not _list_dimension_matches(
        request.topic_codes,
        definition.topic_codes,
        dimension="topic_codes",
        broad_dimensions=broad,
    ):
        return False
    if not _list_dimension_matches(
        request.concept_codes,
        definition.concept_codes,
        dimension="concept_codes",
        broad_dimensions=broad,
    ):
        return False
    if not _list_dimension_matches(
        request.competency_codes,
        definition.competency_codes,
        dimension="competency_codes",
        broad_dimensions=broad,
    ):
        return False
    if not _list_dimension_matches(
        request.learning_outcome_ids,
        definition.learning_outcome_ids,
        dimension="learning_outcome_ids",
        broad_dimensions=broad,
    ):
        return False
    return True


def validate_required_diagnostic_scope(
    request: DiagnosticAuthoringRequest,
) -> list[str]:
    issues: list[str] = []
    if not request.subject_code or not request.grade_year_code:
        issues.append("missing_diagnostic_scope")
    if not (
        request.topic_codes
        or request.concept_codes
        or request.learning_outcome_ids
        or request.competency_codes
    ):
        issues.append("missing_diagnostic_scope")
    return issues
