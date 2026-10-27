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
    diagnostic_validation: list[dict[str, Any]]
    diagnostic_results: list[dict[str, Any]]
    root_cause_results: list[dict[str, Any]]
    diagnostic_tag_repair_item_ids: list[str]
    repair_count_by_item: Annotated[dict[str, int], _merge_dict]
    repair_instructions_by_item: dict[str, list[str]]
    node_attempts: Annotated[dict[str, int], _merge_dict]
    warnings: Annotated[list[str], operator.add]
    errors: list[str]
    status: str
    prompt_versions: dict[str, str]
    gateway_usage: dict[str, Any]
    node_latencies_ms: Annotated[dict[str, float], _merge_dict]
    interrupt_payload: dict[str, Any] | None
    human_decision: dict[str, Any] | None
    human_approved: bool
    diagnostic_human_approved: bool
    human_revalidate: bool
    pipeline_halt: bool
    gateway_retry_required: bool
    gateway_retry_node: str | None
    allow_gateway_retry: bool
    repair_item_ids: list[str]
    generation_call_cache: dict[str, Any]
    audit_refs: Annotated[list[str], operator.add]
    final_result: dict[str, Any] | None
    created_at: str
    updated_at: str
