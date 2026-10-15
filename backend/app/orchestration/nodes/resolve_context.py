from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_intelligence.context_pack import format_citation
from app.knowledge_intelligence.contracts import (
    KnowledgeContextPack,
    KnowledgeEvidenceItem,
    KnowledgeRetrievalRequest,
)
from app.knowledge_intelligence.retrieval import RetrievalError
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.knowledge_intelligence.scope import authority_label_for_source
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import Source, SourceRevision
from app.orchestration.contracts import ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import (
    audit_node,
    get_request,
    next_attempt,
    pipeline_failure,
    timed_update,
)
from app.orchestration.query_text import build_retrieval_query
from app.orchestration.scope_validation import validate_context_scope
from app.orchestration.state import OrchestrationGraphState


def _augment_pack_with_revision(
    session: Session,
    pack: KnowledgeContextPack,
    revision_id: str,
) -> KnowledgeContextPack:
    if any(item.source_revision_id == revision_id for item in pack.evidence):
        return pack
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return pack
    source = session.get(Source, revision.source_id)
    if source is None:
        return pack
    binding = session.scalar(
        select(KnowledgeSourceBinding).where(
            KnowledgeSourceBinding.source_revision_id == revision_id
        )
    )
    snippet = (revision.extracted_text or "").strip()
    if not snippet:
        return pack
    item = KnowledgeEvidenceItem(
        source_id=source.id,
        source_revision_id=revision.id,
        source_revision_checksum=revision.checksum,
        binding_id=binding.id if binding is not None else "",
        trust_tier=source.trust_tier,
        authority_label=authority_label_for_source(source),
        title=source.title,
        locator=source.url or f"source:{source.id}",
        snippet=snippet,
        retrieval_score=0.0,
        retrieval_rank=len(pack.evidence) + 1,
        anythingllm_workspace="",
        anythingllm_document_id=binding.anythingllm_document_id if binding else "",
        citation_label=f"src:{source.id[:8]}/rev:{revision.revision_number}",
    )
    evidence = list(pack.evidence) + [item]
    citations = [format_citation(e) for e in evidence]
    bounded_lines = [
        f"{citation}\n{e.snippet}" for citation, e in zip(citations, evidence, strict=True)
    ]
    return pack.model_copy(
        update={
            "evidence": evidence,
            "citations": citations,
            "bounded_text": "\n\n---\n\n".join(bounded_lines),
            "warnings": list(pack.warnings) + ["fixture_injection_revision_appended"],
        }
    )


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

    try:
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
    except RetrievalError as exc:
        return pipeline_failure(
            deps,
            state,
            "resolve_context",
            started,
            "day7_retrieval_error",
            attempt=attempt,
            issue_codes=[str(exc)],
        )
    except Exception:
        return pipeline_failure(
            deps,
            state,
            "resolve_context",
            started,
            "day7_service_error",
            attempt=attempt,
        )
    pack = deps.knowledge_service.build_context_pack(retrieval)
    if request.fixture_scenario() == "injection_evidence":
        inj_id = request.metadata_json.get("injection_revision_id")
        if isinstance(inj_id, str) and inj_id.strip():
            pack = _augment_pack_with_revision(deps.session, pack, inj_id.strip())
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
