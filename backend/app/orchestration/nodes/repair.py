from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import ReviewVerdict
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
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def repair_planner_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "repair")
    request = get_request(state)
    verdicts = [ReviewVerdict.model_validate(v) for v in state.get("review_verdicts") or []]
    repair_instructions: dict[str, list[str]] = {}
    repair_item_ids: list[str] = []
    for verdict in verdicts:
        if not verdict.repair_instructions:
            continue
        repair_instructions.setdefault(verdict.item_id, []).extend(verdict.repair_instructions)
        repair_item_ids.append(verdict.item_id)

    deterministic = state.get("deterministic_validation") or []
    for summary in deterministic:
        if summary.get("repairable"):
            item_id = str(summary.get("item_id"))
            repair_item_ids.append(item_id)
            repair_instructions.setdefault(item_id, []).append(
                "Address deterministic validation findings: "
                + ",".join(summary.get("issue_codes") or [])
            )

    diagnostic = state.get("diagnostic_validation") or []
    for summary in diagnostic:
        if summary.get("repairable"):
            item_id = str(summary.get("item_id"))
            repair_item_ids.append(item_id)
            existing = repair_instructions.get(item_id, [])
            if not existing:
                repair_instructions.setdefault(item_id, []).append(
                    "Address diagnostic validation findings: "
                    + ",".join(summary.get("issue_codes") or [])
                )

    repair_counts = dict(state.get("repair_count_by_item") or {})
    prompt = get_prompt("repair")
    gateway_usage = dict(state.get("gateway_usage") or {})
    call_cache = dict(state.get("generation_call_cache") or {})
    gen_request = GenerationRequest(
        role=GenerationNodeRole.REPAIR,
        prompt_version=prompt.version,
        system_prompt=prompt.text,
        user_payload={"repair_instructions": repair_instructions},
        output_schema_name="RepairPlan",
        scenario=request.fixture_scenario(),
    )
    response, extra = invoke_generation(
        deps,
        state,
        node_name="repair",
        attempt=attempt,
        request=gen_request,
        run_id=request.run_id,
        item_id=None,
    )
    if extra and "error_code" in extra:
        failure = pipeline_failure(
            deps,
            state,
            "repair_planner",
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
        gateway_usage, response.usage, count_call=not bool(extra and extra.get("cache_hit"))
    )
    if extra and extra.get("cache"):
        call_cache = extra["cache"]

    for item_id in set(repair_item_ids):
        repair_counts[item_id] = repair_counts.get(item_id, 0) + 1

    audit_id = audit_node(
        deps,
        state,
        "repair_planner",
        "ok",
        attempt=attempt,
        prompt_version=prompt.version,
        payload={"items": list(set(repair_item_ids))},
    )
    return timed_update(
        state,
        "repair_planner",
        started,
        {
            "repair_instructions_by_item": repair_instructions,
            "repair_count_by_item": repair_counts,
            "repair_item_ids": list(set(repair_item_ids)),
            "status": OrchestrationRunStatus.REPAIRING.value,
            "gateway_usage": gateway_usage,
            "generation_call_cache": call_cache,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
