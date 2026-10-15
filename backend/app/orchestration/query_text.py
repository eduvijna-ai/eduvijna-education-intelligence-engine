from __future__ import annotations

from app.orchestration.contracts import OrchestrationRequest, ResolvedScope


def build_retrieval_query(request: OrchestrationRequest, scope: ResolvedScope) -> str:
    if request.retrieval_query and request.retrieval_query.strip():
        return request.retrieval_query.strip()
    parts: list[str] = []
    if scope.subject_code:
        parts.append(scope.subject_code)
    if scope.grade_year_code:
        parts.append(scope.grade_year_code)
    if scope.topic_codes:
        parts.extend(scope.topic_codes)
    if scope.concept_codes:
        parts.extend(scope.concept_codes)
    if request.cognitive_target:
        parts.append(request.cognitive_target)
    if request.competency_target:
        parts.append(request.competency_target)
    if not parts:
        raise ValueError("retrieval_query_required_when_scope_cannot_derive_query")
    return " ".join(parts)
