from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.diagnostic_intelligence.service import DiagnosticIntelligenceService

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
)
from app.diagnostic_intelligence.enrichment import build_gateway_user_payload
from app.diagnostic_intelligence.mapping import draft_to_diagnostic_item
from app.diagnostic_intelligence.output_validation import (
    DiagnosticOutputValidationError,
    parse_strict_diagnostic_output,
)
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.diagnostic_intelligence.prompts.registry import get_diagnostic_prompt
from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.contracts import DraftQuestionItem, ResolvedScope, SolverResult
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.diagnostic_audit import persist_diagnostic_item_audit
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


def _scope_metadata(request: DiagnosticAuthoringRequest) -> dict[str, Any]:
    return {
        "curriculum_version_id": request.curriculum_version_id,
        "exam_version_id": request.exam_version_id,
        "subject_code": request.subject_code,
        "grade_year_code": request.grade_year_code,
        "medium_code": request.medium_code,
        "organization_id": request.organization_id,
        "institution_id": request.institution_id,
        "teacher_id": request.teacher_id,
        "actor_id": request.actor_id,
    }


def _build_authoring(
    draft: DraftQuestionItem,
    scope: ResolvedScope,
    request: Any,
    lo_ids: list[str],
    allowed_revision_ids: list[str],
    allowed_evidence_refs: list[str],
) -> DiagnosticAuthoringRequest:
    diagnostic_item = draft_to_diagnostic_item(draft)
    return DiagnosticAuthoringRequest(
        item=diagnostic_item,
        subject_code=scope.subject_code or request.subject_code,
        grade_year_code=scope.grade_year_code or request.grade_year_code,
        topic_codes=list(request.topic_codes),
        concept_codes=list(request.concept_codes),
        learning_outcome_ids=lo_ids,
        competency_codes=list(draft.competency_codes),
        curriculum_version_id=scope.curriculum_version_id,
        exam_version_id=scope.exam_version_id,
        medium_code=scope.medium_code or request.medium_code,
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        teacher_id=scope.teacher_id,
        actor_id=scope.actor_id or request.actor_id,
        allowed_source_revision_ids=allowed_revision_ids,
        allowed_evidence_refs=allowed_evidence_refs,
        fixture_scenario=request.diagnostic_fixture_scenario(),
    )


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
    summaries: list[dict[str, Any]] = list(state.get("diagnostic_validation") or [])
    results_by_id: dict[str, dict[str, Any]] = {
        str(r.get("item_id")): r for r in (state.get("diagnostic_results") or [])
    }
    summaries_by_id: dict[str, dict[str, Any]] = {
        str(s.get("item_id")): s for s in summaries
    }
    repair_instructions = dict(state.get("repair_instructions_by_item") or {})
    repair_counts = dict(state.get("repair_count_by_item") or {})
    audit_refs: list[str] = []
    run_id = str(state.get("run_id") or request.run_id)
    target_ids = set(state.get("diagnostic_tag_repair_item_ids") or [])

    solvers: dict[str, SolverResult] = {}
    for raw in state.get("solver_results") or []:
        solver = SolverResult.model_validate(raw)
        solvers[solver.item_id] = solver

    for raw in state.get("draft_items") or []:
        draft = DraftQuestionItem.model_validate(raw)
        if target_ids and draft.item_id not in target_ids:
            continue

        authoring = _build_authoring(
            draft,
            scope,
            request,
            list(lo_ids) if isinstance(lo_ids, list) else [],
            allowed_revision_ids,
            allowed_evidence_refs,
        )
        preflight = run_diagnostic_preflight(authoring)
        scope_meta = _scope_metadata(authoring)

        if not preflight.allow_model_call:
            verdict_status = preflight.status.value
            audit_id = persist_diagnostic_item_audit(
                deps,
                state,
                item_id=draft.item_id,
                attempt=attempt,
                status=verdict_status,
                taxonomy_version=authoring.taxonomy_version,
                prompt_version=prompt.version,
                misconception_codes=[],
                source_revision_ids=list(draft.source_revision_ids),
                issue_codes=preflight.issue_codes,
                scope_metadata=scope_meta,
                repair_transition="preflight_blocked",
            )
            audit_refs.append(audit_id)
            summary = {
                "item_id": draft.item_id,
                "blocking": preflight.blocking,
                "repairable": preflight.repairable,
                "review_required": preflight.review_required,
                "issue_codes": preflight.issue_codes,
            }
            summaries_by_id[draft.item_id] = summary
            if preflight.status.value != "not_applicable":
                results_by_id[draft.item_id] = {
                    "item_id": draft.item_id,
                    "question_type": draft.question_type,
                    "option_tags": [],
                    "aggregate_status": preflight.status.value,
                    "errors": preflight.issue_codes if preflight.blocking else [],
                    "warnings": preflight.issue_codes,
                    "audit_refs": [audit_id],
                }
            continue

        scenario_map = request.metadata_json.get("diagnostic_fixture_by_item") or {}
        fixture_scenario = str(
            scenario_map.get(draft.item_id) or authoring.fixture_scenario
        )
        authoring = authoring.model_copy(update={"fixture_scenario": fixture_scenario})

        user_payload = build_gateway_user_payload(authoring)
        user_payload["run_id"] = run_id
        user_payload["diagnostic_repair_attempt"] = repair_counts.get(draft.item_id, 0)
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

        try:
            option_tags = parse_strict_diagnostic_output(
                authoring.item, response.parsed, taxonomy_version=authoring.taxonomy_version
            )
        except DiagnosticOutputValidationError as exc:
            return pipeline_failure(
                deps,
                state,
                "diagnostic_enrich",
                started,
                exc.code,
                attempt=attempt,
            )

        parsed = DistractorDiagnosticResult(
            item_id=draft.item_id,
            question_type=draft.question_type,
            option_tags=option_tags,
            taxonomy_version=authoring.taxonomy_version,
            source_revision_ids=list(draft.source_revision_ids),
        )
        verdict = service.validate_result(
            authoring,
            parsed,
            scope=scope,
            request_marks=request.marks,
            draft_item=draft,
            candidate_codes=preflight.candidate_codes,
            solver=solvers.get(draft.item_id),
        )
        enriched = service.attach_validation_status(parsed, verdict)
        audit_id = persist_diagnostic_item_audit(
            deps,
            state,
            item_id=draft.item_id,
            attempt=attempt,
            status=verdict.status.value,
            taxonomy_version=enriched.taxonomy_version,
            prompt_version=prompt.version,
            misconception_codes=[
                t.misconception_code for t in enriched.option_tags if t.misconception_code
            ],
            source_revision_ids=list(draft.source_revision_ids),
            issue_codes=verdict.issue_codes,
            scope_metadata=scope_meta,
            repair_transition=(
                "tag_repair" if target_ids and draft.item_id in target_ids else None
            ),
        )
        audit_refs.append(audit_id)
        enriched.audit_refs = [audit_id]
        summary = {
            "item_id": draft.item_id,
            "blocking": verdict.blocking,
            "repairable": verdict.repairable,
            "review_required": verdict.review_required,
            "issue_codes": verdict.issue_codes,
        }
        summaries_by_id[draft.item_id] = summary
        if verdict.repair_instructions:
            repair_instructions.setdefault(draft.item_id, []).extend(verdict.repair_instructions)
        results_by_id[draft.item_id] = enriched.model_dump(mode="json")

    merged_summaries = list(summaries_by_id.values())
    node_audit = audit_node(
        deps,
        state,
        "diagnostic_enrich",
        "ok",
        attempt=attempt,
        prompt_version=prompt.version,
        payload={"items": len(merged_summaries)},
    )
    audit_refs.append(node_audit)
    return timed_update(
        state,
        "diagnostic_enrich",
        started,
        {
            "diagnostic_validation": merged_summaries,
            "diagnostic_results": list(results_by_id.values()),
            "repair_instructions_by_item": repair_instructions,
            "diagnostic_tag_repair_item_ids": [],
            "gateway_usage": gateway_usage,
            "generation_call_cache": call_cache,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "audit_refs": audit_refs,
        },
        attempt_map=attempt_map,
    )
