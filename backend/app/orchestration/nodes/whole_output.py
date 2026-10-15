from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import (
    DraftQuestionItem,
    OrchestrationResult,
    ResolvedScope,
    utc_now,
)
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.state import OrchestrationGraphState


def whole_output_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    deterministic = state.get("deterministic_validation") or []
    duplicate = state.get("duplicate_validation") or []
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]

    blocking = any(item.get("blocking") for item in deterministic)
    duplicate_block = any(item.get("is_duplicate") for item in duplicate)
    repair_counts = state.get("repair_count_by_item") or {}
    exhausted = any(
        count > request.effective_max_repairs() for count in repair_counts.values()
    )

    approved_items: list[DraftQuestionItem] = []
    if not blocking and not duplicate_block and not exhausted:
        approved_items = drafts

    status = OrchestrationRunStatus.COMPLETED
    errors = list(state.get("errors") or [])
    if blocking or duplicate_block:
        status = OrchestrationRunStatus.FAILED
        if duplicate_block:
            errors.append("duplicate_reject")
        if blocking:
            errors.append("validation_reject")
    if exhausted:
        status = OrchestrationRunStatus.REVIEW_REQUIRED
        errors.append("repair_exhausted")

    approved_mismatch = (
        status == OrchestrationRunStatus.COMPLETED
        and len(approved_items) != request.requested_count
    )
    if approved_mismatch:
        status = OrchestrationRunStatus.FAILED
        errors.append("approved_count_mismatch")

    revision_ids: list[str] = []
    for item in approved_items:
        revision_ids.extend(item.source_revision_ids)

    result = OrchestrationResult(
        run_id=state["run_id"],
        status=status,
        requested_count=request.requested_count,
        approved_count=len(approved_items),
        items=approved_items,
        source_revision_ids=sorted(set(revision_ids)),
        retrieval_profile_version=request.retrieval_profile_version,
        prompt_versions=state.get("prompt_versions") or {},
        repair_summary={k: int(v) for k, v in repair_counts.items()},
        warnings=list(state.get("warnings") or []),
        errors=errors,
        audit_refs=[],
        request_hash=state.get("request_hash", request.request_hash()),
        started_at=utc_now(),
        completed_at=utc_now(),
        gateway_usage=state.get("gateway_usage") or {},
        metadata_json={"institution_id": scope.institution_id},
    )
    audit_node(deps, state, "whole_output", status.value)
    return timed_update(
        state,
        "whole_output",
        started,
        {
            "final_result": result.model_dump(mode="json"),
            "status": status.value,
            "errors": errors,
        },
    )
