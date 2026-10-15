from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import DraftQuestionItem, GenerationPlan, SolverResult
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
from app.orchestration.nodes.author import _target_item_ids
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def solver_node(state: OrchestrationGraphState, deps: OrchestrationDependencies) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "solver")
    request = get_request(state)
    plan = GenerationPlan.model_validate(state.get("generation_plan") or {"items": []})
    targets = set(_target_item_ids(state, plan))
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    prompt = get_prompt("solver")
    results: dict[str, dict[str, Any]] = {}
    for raw in state.get("solver_results") or []:
        parsed = SolverResult.model_validate(raw)
        if parsed.item_id not in targets:
            results[parsed.item_id] = raw
    gateway_usage = dict(state.get("gateway_usage") or {})
    call_cache = dict(state.get("generation_call_cache") or {})
    audit_refs: list[str] = []

    for draft in drafts:
        if draft.item_id not in targets:
            continue
        stem_only = {
            "item_id": draft.item_id,
            "stem_text": draft.stem_text,
            "question_type": draft.question_type,
            "options": [{"option_key": o.option_key, "text": o.text} for o in draft.options],
        }
        gen_request = GenerationRequest(
            role=GenerationNodeRole.SOLVER,
            prompt_version=prompt.version,
            system_prompt=prompt.text,
            user_payload={"run_id": request.run_id, **stem_only},
            output_schema_name="SolverResult",
            scenario=request.fixture_scenario(),
        )
        response, extra = invoke_generation(
            deps,
            state,
            node_name="solver",
            attempt=attempt,
            request=gen_request,
            run_id=request.run_id,
            item_id=draft.item_id,
        )
        if extra and "error_code" in extra:
            failure = pipeline_failure(
                deps, state, "solver", started, extra["error_code"], attempt=attempt
            )
            if extra.get("audit_refs"):
                failure["audit_refs"] = list(failure.get("audit_refs") or []) + extra["audit_refs"]
            return failure
        assert response is not None
        if extra and extra.get("audit_refs"):
            audit_refs.extend(extra["audit_refs"])
        if extra and extra.get("cache"):
            call_cache = extra["cache"]
        gateway_usage = merge_gateway_usage(gateway_usage, response.usage)
        solver = SolverResult.model_validate(response.parsed)
        results[draft.item_id] = solver.model_dump(mode="json")

    ordered = [results[d.item_id] for d in drafts if d.item_id in results]
    return timed_update(
        state,
        "solver",
        started,
        {
            "solver_results": ordered,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "prompt_versions": {**(state.get("prompt_versions") or {}), "solver": prompt.version},
            "gateway_usage": gateway_usage,
            "generation_call_cache": call_cache,
            "audit_refs": audit_refs,
        },
        attempt_map=attempt_map,
    )
