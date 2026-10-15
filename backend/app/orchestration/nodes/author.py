from __future__ import annotations

import time
from typing import Any

from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.contracts import DraftQuestionItem, GenerationPlan
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationRequest
from app.orchestration.gateway_invoke import invoke_generation
from app.orchestration.nodes._helpers import (
    get_request,
    next_attempt,
    pipeline_failure,
    timed_update,
)
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def _target_item_ids(state: OrchestrationGraphState, plan: GenerationPlan) -> list[str]:
    repair_ids = list(state.get("repair_item_ids") or [])
    if repair_ids:
        return repair_ids
    return [item.item_id for item in plan.items]


def author_node(state: OrchestrationGraphState, deps: OrchestrationDependencies) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "author")
    request = get_request(state)
    plan = GenerationPlan.model_validate(state.get("generation_plan") or {"items": []})
    context = KnowledgeContextPack.model_validate(state.get("knowledge_context") or {})
    allowed_revision_ids = [item.source_revision_id for item in context.evidence]
    lo_ids = request.metadata_json.get("learning_outcome_ids", [])
    if isinstance(lo_ids, str):
        lo_ids = [lo_ids]
    prompt = get_prompt("author")
    existing: dict[str, DraftQuestionItem] = {}
    for raw in state.get("draft_items") or []:
        item = DraftQuestionItem.model_validate(raw)
        existing[item.item_id] = item
    targets = _target_item_ids(state, plan)
    drafts: dict[str, dict[str, Any]] = {
        item_id: existing[item_id].model_dump(mode="json")
        for item_id in existing
        if item_id not in targets
    }
    gateway_usage = dict(state.get("gateway_usage") or {})
    call_cache = dict(state.get("generation_call_cache") or {})
    audit_refs: list[str] = []

    for slot in plan.items:
        if slot.item_id not in targets:
            continue
        repair_instructions = (state.get("repair_instructions_by_item") or {}).get(
            slot.item_id, []
        )
        gen_request = GenerationRequest(
            role=GenerationNodeRole.AUTHOR,
            prompt_version=prompt.version,
            system_prompt=prompt.text,
            user_payload={
                "run_id": request.run_id,
                "item_id": slot.item_id,
                "allowed_source_revision_ids": allowed_revision_ids,
                "learning_outcome_ids": lo_ids,
                "marks": request.marks,
                "bounded_context": context.bounded_text,
                "repair_instructions": repair_instructions,
            },
            output_schema_name="DraftQuestionItem",
            scenario=request.fixture_scenario(),
        )
        response, extra = invoke_generation(
            deps,
            state,
            node_name="author",
            attempt=attempt,
            request=gen_request,
            run_id=request.run_id,
            item_id=slot.item_id,
            schema_payload_merge={"slot_index": slot.slot_index},
        )
        if extra and "error_code" in extra:
            failure = pipeline_failure(
                deps,
                state,
                "author",
                started,
                extra["error_code"],
                attempt=attempt,
                retryable=bool(extra.get("retryable")),
            )
            if extra.get("audit_refs"):
                failure["audit_refs"] = list(failure.get("audit_refs") or []) + extra["audit_refs"]
            return failure
        assert response is not None
        if extra and extra.get("audit_refs"):
            audit_refs.extend(extra["audit_refs"])
        if extra and extra.get("cache"):
            call_cache = extra["cache"]
        gateway_usage = merge_gateway_usage(
            gateway_usage, response.usage, count_call=not bool(extra and extra.get("cache_hit"))
        )
        draft = DraftQuestionItem.model_validate(response.parsed)
        if draft.item_id != slot.item_id:
            return pipeline_failure(
                deps,
                state,
                "author",
                started,
                "model_identity_mismatch",
                attempt=attempt,
            )
        drafts[slot.item_id] = draft.model_dump(mode="json")

    ordered = []
    for slot in plan.items:
        if slot.item_id in drafts:
            ordered.append(drafts[slot.item_id])
    return timed_update(
        state,
        "author",
        started,
        {
            "draft_items": ordered,
            "status": OrchestrationRunStatus.SOLVING.value,
            "prompt_versions": {**(state.get("prompt_versions") or {}), "author": prompt.version},
            "gateway_usage": gateway_usage,
            "generation_call_cache": call_cache,
            "audit_refs": audit_refs,
        },
        attempt_map=attempt_map,
    )
