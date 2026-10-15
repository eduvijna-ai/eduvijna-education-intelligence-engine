from __future__ import annotations

import time
from typing import Any

from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.orchestration.contracts import ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.state import OrchestrationGraphState


def resolve_context_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    if scope.scope_errors:
        return timed_update(
            state,
            "resolve_context",
            started,
            {"status": OrchestrationRunStatus.FAILED.value},
        )

    query = request.retrieval_query or "synthetic orchestration retrieval query"
    retrieval = deps.knowledge_service.retrieve(
        KnowledgeRetrievalRequest(
            query_text=query,
            organization_id=scope.organization_id,
            institution_id=scope.institution_id,
            curriculum_version_id=None,
            exam_version_id=None,
            topic_codes=request.topic_codes,
            concept_codes=request.concept_codes,
            retrieval_profile_version=request.retrieval_profile_version
            or DEFAULT_RETRIEVAL_PROFILE_VERSION,
            actor_id=scope.actor_id,
        )
    )
    pack = deps.knowledge_service.build_context_pack(retrieval)
    revision_ids = [item.source_revision_id for item in pack.evidence]
    audit_node(
        deps,
        state,
        "resolve_context",
        "ok",
        source_revision_ids=revision_ids,
        payload={"warnings": pack.warnings},
    )
    warnings = list(pack.warnings)
    if request.fixture_scenario() == "foreign_tenant" and pack.evidence:
        warnings.append("foreign_tenant_context_attempt")
    update = {
        "knowledge_context": pack.model_dump(mode="json"),
        "warnings": warnings,
        "status": OrchestrationRunStatus.PLANNING.value,
    }
    return timed_update(state, "resolve_context", started, update)
