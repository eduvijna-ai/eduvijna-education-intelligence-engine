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
from app.orchestration.nodes._helpers import audit_node, get_request, next_attempt, timed_update
from app.orchestration.state import OrchestrationGraphState


def whole_output_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "whole_output")
    request = get_request(state)
    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    deterministic = state.get("deterministic_validation") or []
    duplicate = state.get("duplicate_validation") or []
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    errors = list(state.get("errors") or [])

    blocking = any(item.get("blocking") for item in deterministic)
    duplicate_block = any(item.get("is_duplicate") for item in duplicate)
    repair_counts = state.get("repair_count_by_item") or {}
    exhausted = any(count > request.effective_max_repairs() for count in repair_counts.values())
    review_required = any(item.get("review_required") for item in deterministic)
    human_approved = bool(state.get("human_approved"))

    if state.get("pipeline_halt") or state.get("status") == OrchestrationRunStatus.FAILED.value:
        status = OrchestrationRunStatus.FAILED
    elif duplicate_block:
        status = OrchestrationRunStatus.FAILED
        errors.append("duplicate_reject")
    elif blocking:
        status = OrchestrationRunStatus.FAILED
        errors.append("validation_reject")
    elif exhausted:
        status = OrchestrationRunStatus.REVIEW_REQUIRED
        errors.append("repair_exhausted")
    elif review_required and not human_approved:
        status = OrchestrationRunStatus.REVIEW_REQUIRED
        errors.append("review_required_unresolved")
    else:
        status = OrchestrationRunStatus.COMPLETED

    approved_items: list[DraftQuestionItem] = []
    if status == OrchestrationRunStatus.COMPLETED:
        approved_items = drafts

    if (
        status == OrchestrationRunStatus.COMPLETED
        and len(approved_items) != request.requested_count
    ):
        status = OrchestrationRunStatus.FAILED
        errors.append("approved_count_mismatch")

    if errors and status == OrchestrationRunStatus.COMPLETED:
        status = OrchestrationRunStatus.FAILED

    revision_ids: list[str] = []
    for item in approved_items:
        revision_ids.extend(item.source_revision_ids)

    audit_id = audit_node(
        deps,
        state,
        "whole_output",
        status.value,
        attempt=attempt,
        payload={"approved": len(approved_items)},
    )
    audit_refs = list(state.get("audit_refs") or []) + [audit_id]

    result = OrchestrationResult(
        run_id=str(state.get("run_id") or request.run_id),
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
        audit_refs=audit_refs,
        request_hash=state.get("request_hash", request.request_hash()),
        started_at=utc_now(),
        completed_at=utc_now() if status != OrchestrationRunStatus.REVIEW_REQUIRED else None,
        gateway_usage=state.get("gateway_usage") or {},
        metadata_json={"institution_id": scope.institution_id},
    )
    return timed_update(
        state,
        "whole_output",
        started,
        {
            "final_result": result.model_dump(mode="json"),
            "status": status.value,
            "errors": errors,
            "audit_refs": audit_refs,
        },
        attempt_map=attempt_map,
    )
