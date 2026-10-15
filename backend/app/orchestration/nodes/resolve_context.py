from __future__ import annotations

import time
from typing import Any

from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.orchestration.contracts import ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, get_request, next_attempt, timed_update
from app.orchestration.query_text import build_retrieval_query
from app.orchestration.scope_validation import validate_context_scope
from app.orchestration.state import OrchestrationGraphState


def resolve_context_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "resolve_context")
    request = get_request(state)
    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    if scope.scope_errors:
        return timed_update(
            state,
            "resolve_context",
            started,
            {
                "status": OrchestrationRunStatus.FAILED.value,
                "pipeline_halt": True,
            },
            attempt_map=attempt_map,
        )

    try:
        query = build_retrieval_query(request, scope)
    except ValueError:
        audit_id = audit_node(
            deps,
            state,
            "resolve_context",
            "failed",
            attempt=attempt,
            issue_codes=["retrieval_query_missing"],
        )
        return timed_update(
            state,
            "resolve_context",
            started,
            {
                "status": OrchestrationRunStatus.FAILED.value,
                "errors": ["retrieval_query_missing"],
                "pipeline_halt": True,
                "audit_refs": [audit_id],
            },
            attempt_map=attempt_map,
        )

    retrieval = deps.knowledge_service.retrieve(
        KnowledgeRetrievalRequest(
            query_text=query,
            organization_id=scope.organization_id,
            institution_id=scope.institution_id,
            teacher_id=scope.teacher_id,
            curriculum_version_id=scope.curriculum_version_id,
            exam_version_id=scope.exam_version_id,
            grade_year_code=scope.grade_year_code,
            medium_code=scope.medium_code,
            subject_code=scope.subject_code,
            topic_codes=scope.topic_codes,
            concept_codes=scope.concept_codes,
            retrieval_profile_version=request.retrieval_profile_version
            or DEFAULT_RETRIEVAL_PROFILE_VERSION,
            actor_id=scope.actor_id,
        )
    )
    pack = deps.knowledge_service.build_context_pack(retrieval)
    scope_issues = validate_context_scope(scope, pack)
    revision_ids = [item.source_revision_id for item in pack.evidence]
    if scope_issues:
        audit_id = audit_node(
            deps,
            state,
            "resolve_context",
            "failed",
            attempt=attempt,
            source_revision_ids=revision_ids,
            issue_codes=scope_issues,
            payload={"warnings": pack.warnings},
        )
        return timed_update(
            state,
            "resolve_context",
            started,
            {
                "knowledge_context": pack.model_dump(mode="json"),
                "status": OrchestrationRunStatus.FAILED.value,
                "errors": scope_issues,
                "pipeline_halt": True,
                "warnings": list(pack.warnings),
                "audit_refs": [audit_id],
            },
            attempt_map=attempt_map,
        )

    audit_id = audit_node(
        deps,
        state,
        "resolve_context",
        "ok",
        attempt=attempt,
        source_revision_ids=revision_ids,
        payload={"warnings": pack.warnings, "query_text": query},
    )
    return timed_update(
        state,
        "resolve_context",
        started,
        {
            "knowledge_context": pack.model_dump(mode="json"),
            "warnings": list(pack.warnings),
            "status": OrchestrationRunStatus.PLANNING.value,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
