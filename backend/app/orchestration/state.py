from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = dict(left or {})
    if right:
        merged.update(right)
    return merged


class OrchestrationGraphState(TypedDict, total=False):
    run_id: str
    thread_id: str
    request: dict[str, Any]
    request_hash: str
    resolved_scope: dict[str, Any]
    generation_plan: dict[str, Any]
    knowledge_context: dict[str, Any]
    draft_items: list[dict[str, Any]]
    solver_results: list[dict[str, Any]]
    review_verdicts: list[dict[str, Any]]
    deterministic_validation: list[dict[str, Any]]
    duplicate_validation: list[dict[str, Any]]
    repair_count_by_item: Annotated[dict[str, int], _merge_dict]
    repair_instructions_by_item: dict[str, list[str]]
    node_attempts: Annotated[dict[str, int], _merge_dict]
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    status: str
    prompt_versions: dict[str, str]
    gateway_usage: dict[str, Any]
    node_latencies_ms: Annotated[dict[str, float], _merge_dict]
    interrupt_payload: dict[str, Any] | None
    final_result: dict[str, Any] | None
    created_at: str
    updated_at: str
