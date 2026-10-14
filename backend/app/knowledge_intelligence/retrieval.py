from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterError, AdapterRetrievalRequest
from app.knowledge_intelligence.audit import hash_query_text, new_query_id, record_audit_event
from app.knowledge_intelligence.binding_match import build_binding_lookup, match_binding_for_hit
from app.knowledge_intelligence.contracts import (
    AppliedKnowledgeScope,
    KnowledgeEvidenceItem,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
)
from app.knowledge_intelligence.enums import KnowledgeAuditEventType, KnowledgeIndexStatus
from app.knowledge_intelligence.retrieval_profile import RetrievalProfile, load_retrieval_profile
from app.knowledge_intelligence.scope import (
    authority_label_for_source,
    binding_visible_to_request,
    scope_from_source,
)
from app.knowledge_intelligence.scope_verify import local_scope_passes
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import Source, SourceRevision


class RetrievalError(ValueError):
    pass


def _validate_request(request: KnowledgeRetrievalRequest, profile: RetrievalProfile) -> None:
    if request.retrieval_profile_version != profile.version:
        raise RetrievalError("retrieval_profile_version mismatch")
    if request.top_k > profile.default_top_k * 4:
        raise RetrievalError("top_k exceeds allowed bound for profile")
    tenant_scoped = any(
        [request.organization_id, request.institution_id, request.teacher_id]
    )
    if tenant_scoped and request.organization_id is None:
        raise RetrievalError("organization_id required when tenant scope is partial")


def compile_scope_filters(request: KnowledgeRetrievalRequest) -> dict[str, str | list[str]]:
    """Adapter hints only; authoritative scope checks happen locally (D7-R07)."""
    return {}


def _authority_rank(trust_tier: str) -> int:
    order = {
        "official_primary": 0,
        "official_supporting": 1,
        "analytical": 2,
        "institution": 3,
        "teacher": 4,
    }
    return order.get(trust_tier, 99)


def _citation_label(source: Source, revision: SourceRevision) -> str:
    return f"src:{source.id[:8]}/rev:{revision.revision_number}"


def retrieve_knowledge(
    session: Session,
    adapter: AnythingLLMAdapter,
    request: KnowledgeRetrievalRequest,
) -> KnowledgeRetrievalResult:
    profile = load_retrieval_profile(request.retrieval_profile_version)
    _validate_request(request, profile)

    bindings = list(
        session.scalars(
            select(KnowledgeSourceBinding).where(
                KnowledgeSourceBinding.index_status == KnowledgeIndexStatus.ACTIVE.value,
                KnowledgeSourceBinding.retrieval_profile_version == profile.version,
            )
        )
    )
    visible_bindings = [
        binding
        for binding in bindings
        if binding_visible_to_request(
            scope_from_source(_require_source(session, binding.source_id)),
            organization_id=request.organization_id,
            institution_id=request.institution_id,
            teacher_id=request.teacher_id,
        )
    ]
    workspaces = sorted({binding.anythingllm_workspace for binding in visible_bindings})
    warnings: list[str] = []
    if not workspaces:
        warnings.append("no_active_bindings_for_scope")
        result = KnowledgeRetrievalResult(
            query_id=new_query_id(),
            query_text=request.query_text,
            retrieval_profile_version=profile.version,
            items=[],
            scope_applied=AppliedKnowledgeScope(
                organization_id=request.organization_id,
                institution_id=request.institution_id,
                teacher_id=request.teacher_id,
                curriculum_version_id=request.curriculum_version_id,
                exam_version_id=request.exam_version_id,
                grade_year_code=request.grade_year_code,
                medium_code=request.medium_code,
                subject_code=request.subject_code,
                topic_codes=request.topic_codes,
                concept_codes=request.concept_codes,
                source_authority_tiers=request.source_authority_tiers,
                workspaces_queried=[],
            ),
            warnings=warnings,
            created_at=datetime.now(UTC),
        )
        _audit_retrieval(session, request, result, errors=[])
        return result

    adapter_request = AdapterRetrievalRequest(
        query_text=request.query_text,
        top_k=request.top_k,
        workspace_slugs=tuple(workspaces),
        metadata_filters=compile_scope_filters(request),
    )
    errors: list[str] = []
    try:
        hits = adapter.retrieve(adapter_request)
    except AdapterError as exc:
        errors.append(exc.message)
        hits = []
        warnings.append("gateway_unavailable")

    binding_by_doc = build_binding_lookup(visible_bindings)

    items: list[KnowledgeEvidenceItem] = []
    dropped_foreign = 0
    scope_verification_warnings: list[str] = []
    verified_filters: dict[str, str | list[str]] = {}
    for hit in hits:
        doc_source_meta = (hit.metadata or {}).get("docSource")
        if not isinstance(doc_source_meta, str) or not doc_source_meta.strip():
            warnings.append("missing_doc_source")
            continue
        matched_binding = match_binding_for_hit(hit, binding_by_doc)
        if matched_binding is None:
            warnings.append(f"unknown_remote_document:{doc_source_meta}")
            continue
        source = _require_source(session, matched_binding.source_id)
        revision = session.get(SourceRevision, matched_binding.source_revision_id)
        if revision is None:
            warnings.append(f"missing_revision:{matched_binding.source_revision_id}")
            continue
        if revision.checksum != matched_binding.source_revision_checksum:
            warnings.append(f"stale_checksum:{matched_binding.source_revision_id}")
            continue
        if revision.status != "active":
            warnings.append(f"inactive_revision:{matched_binding.source_revision_id}")
            continue
        if not binding_visible_to_request(
            scope_from_source(source),
            organization_id=request.organization_id,
            institution_id=request.institution_id,
            teacher_id=request.teacher_id,
        ):
            dropped_foreign += 1
            continue
        if hit.score < profile.score_threshold:
            continue
        authority_label = authority_label_for_source(source)
        if (
            request.source_authority_tiers
            and source.trust_tier not in request.source_authority_tiers
        ):
            continue
        passes_scope, entity_refs, local_warnings = local_scope_passes(
            session, source, revision, request
        )
        scope_verification_warnings.extend(local_warnings)
        if not passes_scope:
            for warning in local_warnings:
                if warning.startswith("dropped_"):
                    warnings.append(f"{warning}:{revision.id}")
            continue
        for key, value in entity_refs.items():
            verified_filters[key] = value
        items.append(
            KnowledgeEvidenceItem(
                source_id=source.id,
                source_revision_id=revision.id,
                source_revision_checksum=revision.checksum,
                binding_id=matched_binding.id,
                trust_tier=source.trust_tier,
                authority_label=authority_label,
                title=source.title,
                locator=source.url or f"source:{source.id}",
                snippet=hit.text,
                retrieval_score=hit.score,
                retrieval_rank=hit.rank,
                anythingllm_workspace=hit.workspace_slug,
                anythingllm_document_id=matched_binding.anythingllm_document_id or hit.document_id,
                entity_refs=entity_refs,
                citation_label=_citation_label(source, revision),
            )
        )

    if profile.deduplicate:
        items = _deduplicate_items(items)
    if profile.prefer_official_authority:
        items.sort(
            key=lambda item: (
                _authority_rank(item.trust_tier),
                -item.retrieval_score,
                item.source_revision_id,
            )
        )
    else:
        items.sort(key=lambda item: (-item.retrieval_score, item.source_revision_id))
    items = items[: request.top_k]

    result = KnowledgeRetrievalResult(
        query_id=new_query_id(),
        query_text=request.query_text,
        retrieval_profile_version=profile.version,
        items=items,
        scope_applied=AppliedKnowledgeScope(
            organization_id=request.organization_id,
            institution_id=request.institution_id,
            teacher_id=request.teacher_id,
            curriculum_version_id=verified_filters.get("curriculum_version_id")
            if isinstance(verified_filters.get("curriculum_version_id"), str)
            else request.curriculum_version_id,
            exam_version_id=verified_filters.get("exam_version_id")
            if isinstance(verified_filters.get("exam_version_id"), str)
            else request.exam_version_id,
            grade_year_code=request.grade_year_code,
            medium_code=request.medium_code,
            subject_code=request.subject_code,
            topic_codes=request.topic_codes,
            concept_codes=request.concept_codes,
            source_authority_tiers=request.source_authority_tiers,
            workspaces_queried=workspaces,
            verified_filters=verified_filters,
            scope_verification_warnings=sorted(set(scope_verification_warnings)),
        ),
        warnings=warnings,
        dropped_foreign_tenant_count=dropped_foreign,
        created_at=datetime.now(UTC),
    )
    _audit_retrieval(session, request, result, errors=errors)
    return result


def _deduplicate_items(items: list[KnowledgeEvidenceItem]) -> list[KnowledgeEvidenceItem]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[KnowledgeEvidenceItem] = []
    for item in items:
        key = (item.source_revision_id, item.anythingllm_document_id, item.snippet[:120])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _require_source(session: Session, source_id: str) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise RetrievalError(f"Missing source {source_id}")
    return source


def _audit_retrieval(
    session: Session,
    request: KnowledgeRetrievalRequest,
    result: KnowledgeRetrievalResult,
    *,
    errors: list[str],
) -> None:
    record_audit_event(
        session,
        event_type=KnowledgeAuditEventType.RETRIEVE,
        query_id=result.query_id,
        query_hash=hash_query_text(request.query_text),
        organization_id=request.organization_id,
        institution_id=request.institution_id,
        teacher_id=request.teacher_id,
        actor_id=request.actor_id,
        retrieval_profile_version=result.retrieval_profile_version,
        workspaces_queried=result.scope_applied.workspaces_queried,
        source_revision_ids=[item.source_revision_id for item in result.items],
        warnings=result.warnings,
        errors=errors,
        payload={
            "dropped_foreign_tenant_count": result.dropped_foreign_tenant_count,
            "result_count": len(result.items),
        },
    )
