from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.diagnostic_intelligence.service import DiagnosticIntelligenceService

from app.diagnostic_intelligence.audit import record_diagnostic_audit_event
from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest
from app.diagnostic_intelligence.enrichment import (
    build_gateway_user_payload,
    parse_model_diagnostic_payload,
)
from app.diagnostic_intelligence.mapping import draft_to_diagnostic_item
from app.diagnostic_intelligence.prompts.registry import get_diagnostic_prompt
from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.contracts import DraftQuestionItem, ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationRequest
from app.orchestration.gateway_invoke import invoke_generation
from app.orchestration.nodes._helpers import (
    audit_node,
    get_request,
    next_attempt,
    pipeline_failure,
    timed_update,
)
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def _diagnostic_service(deps: OrchestrationDependencies) -> DiagnosticIntelligenceService:
    from app.diagnostic_intelligence.service import DiagnosticIntelligenceService

    return DiagnosticIntelligenceService(education_service=deps.education_service)


def diagnostic_enrich_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "diagnostic_enrich")
    request = get_request(state)
    if not request.diagnostic_enrichment_enabled():
        return timed_update(
            state,
            "diagnostic_enrich",
            started,
            {
                "diagnostic_validation": [],
                "diagnostic_results": [],
                "status": state.get("status") or OrchestrationRunStatus.REVIEWING.value,
            },
            attempt_map=attempt_map,
        )

    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    context = KnowledgeContextPack.model_validate(state.get("knowledge_context") or {})
    allowed_revision_ids = [item.source_revision_id for item in context.evidence]
    allowed_evidence_refs = [item.citation_label for item in context.evidence]
    lo_ids = request.metadata_json.get("learning_outcome_ids", [])
    if isinstance(lo_ids, str):
        lo_ids = [lo_ids]

    service = _diagnostic_service(deps)
    prompt = get_diagnostic_prompt()
    gateway_usage = dict(state.get("gateway_usage") or {})
    call_cache = dict(state.get("generation_call_cache") or {})
    summaries: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    repair_instructions = dict(state.get("repair_instructions_by_item") or {})
    audit_refs: list[str] = []
    run_id = str(state.get("run_id") or request.run_id)

    for raw in state.get("draft_items") or []:
        draft = DraftQuestionItem.model_validate(raw)
        diagnostic_item = draft_to_diagnostic_item(draft)
        authoring = DiagnosticAuthoringRequest(
            item=diagnostic_item,
            subject_code=scope.subject_code or request.subject_code,
            grade_year_code=scope.grade_year_code or request.grade_year_code,
            topic_codes=request.topic_codes,
            concept_codes=request.concept_codes,
            learning_outcome_ids=list(lo_ids) if isinstance(lo_ids, list) else [],
            competency_codes=draft.competency_codes,
            organization_id=scope.organization_id,
            institution_id=scope.institution_id,
            allowed_source_revision_ids=allowed_revision_ids,
            allowed_evidence_refs=allowed_evidence_refs,
            fixture_scenario=request.diagnostic_fixture_scenario(),
        )
        user_payload = build_gateway_user_payload(authoring)
        user_payload["run_id"] = run_id
        gen_request = GenerationRequest(
            role=GenerationNodeRole.DIAGNOSTIC,
            prompt_version=prompt.version,
            system_prompt=prompt.text,
            user_payload=user_payload,
            output_schema_name="DiagnosticEnrichmentOutput",
            scenario=request.fixture_scenario(),
        )
        response, extra = invoke_generation(
            deps,
            state,
            node_name="diagnostic_enrich",
            attempt=attempt,
            request=gen_request,
            run_id=run_id,
            item_id=draft.item_id,
        )
        if extra and "error_code" in extra:
            failure = pipeline_failure(
                deps,
                state,
                "diagnostic_enrich",
                started,
                extra["error_code"],
                attempt=attempt,
                retryable=bool(extra.get("retryable")),
            )
            if extra.get("audit_refs"):
                failure["audit_refs"] = list(failure.get("audit_refs") or []) + extra["audit_refs"]
            return failure
        assert response is not None
        gateway_usage = merge_gateway_usage(
            gateway_usage,
            response.usage,
            count_call=not bool(extra and extra.get("cache_hit")),
        )
        if extra and extra.get("cache"):
            call_cache = extra["cache"]

        parsed = parse_model_diagnostic_payload(diagnostic_item, response.parsed)
        verdict = service.validate_result(
            authoring,
            parsed,
            scope=scope,
            request_marks=request.marks,
            draft_item=draft,
        )
        enriched = service.attach_validation_status(parsed, verdict)
        event_id = record_diagnostic_audit_event(
            run_id=run_id,
            item_id=draft.item_id,
            taxonomy_version=enriched.taxonomy_version,
            prompt_version=prompt.version,
            misconception_codes=[
                t.misconception_code for t in enriched.option_tags if t.misconception_code
            ],
            issue_codes=verdict.issue_codes,
            status=verdict.status.value,
        )
        audit_refs.append(event_id)
        summaries.append(
            {
                "item_id": draft.item_id,
                "blocking": verdict.blocking,
                "repairable": verdict.repairable,
                "review_required": verdict.review_required,
                "issue_codes": verdict.issue_codes,
            }
        )
        if verdict.repair_instructions:
            repair_instructions.setdefault(draft.item_id, []).extend(verdict.repair_instructions)
        results.append(enriched.model_dump(mode="json"))

    node_audit = audit_node(
        deps,
        state,
        "diagnostic_enrich",
        "ok",
        attempt=attempt,
        prompt_version=prompt.version,
        payload={"items": len(summaries)},
    )
    audit_refs.append(node_audit)
    return timed_update(
        state,
        "diagnostic_enrich",
        started,
        {
            "diagnostic_validation": summaries,
            "diagnostic_results": results,
            "repair_instructions_by_item": repair_instructions,
            "gateway_usage": gateway_usage,
            "generation_call_cache": call_cache,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "audit_refs": audit_refs,
        },
        attempt_map=attempt_map,
    )
