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
from app.orchestration.diagnostic_routing import diagnostics_finished
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
    diagnostic = state.get("diagnostic_validation") or []
    duplicate = state.get("duplicate_validation") or []
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    errors = list(state.get("errors") or [])

    blocking = any(item.get("blocking") for item in deterministic) or any(
        item.get("blocking") for item in diagnostic
    )
    duplicate_block = any(item.get("is_duplicate") for item in duplicate)
    repair_counts = state.get("repair_count_by_item") or {}
    exhausted = any(count > request.effective_max_repairs() for count in repair_counts.values())
    deterministic_review = any(item.get("review_required") for item in deterministic)
    diagnostic_review = any(item.get("review_required") for item in diagnostic)
    human_approved = bool(state.get("human_approved"))
    diagnostic_human_approved = bool(state.get("diagnostic_human_approved"))

    if state.get("gateway_retry_required"):
        status = OrchestrationRunStatus.RETRY_REQUIRED
    elif state.get("pipeline_halt") or state.get("status") == OrchestrationRunStatus.FAILED.value:
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
    elif deterministic_review and not human_approved:
        status = OrchestrationRunStatus.REVIEW_REQUIRED
        errors.append("review_required_unresolved")
    elif diagnostic_review and not diagnostic_human_approved:
        status = OrchestrationRunStatus.REVIEW_REQUIRED
        errors.append("diagnostic_review_required_unresolved")
    elif not diagnostics_finished(state, request) and request.diagnostic_enrichment_enabled():
        status = OrchestrationRunStatus.REVIEW_REQUIRED
        errors.append("diagnostic_enrichment_incomplete")
    elif request.root_cause_enrichment_enabled():
        eligible_raw = state.get("root_cause_eligible_tag_count")
        eligible = int(eligible_raw) if isinstance(eligible_raw, int) else 0
        produced = len(state.get("root_cause_results") or [])
        root_cause_results = state.get("root_cause_results") or []
        rc_non_pass = any(
            str(entry.get("verdict_status")) != "pass" for entry in root_cause_results
        )
        if rc_non_pass:
            status = OrchestrationRunStatus.REVIEW_REQUIRED
            errors.append("root_cause_review_required")
        elif eligible > 0 and produced < eligible:
            status = OrchestrationRunStatus.REVIEW_REQUIRED
            errors.append("root_cause_enrichment_incomplete")
        elif eligible == 0 and produced == 0:
            status = OrchestrationRunStatus.COMPLETED
        else:
            status = OrchestrationRunStatus.COMPLETED
    else:
        status = OrchestrationRunStatus.COMPLETED

    approved_items: list[DraftQuestionItem] = []
    if status == OrchestrationRunStatus.COMPLETED:
        if request.marks is not None:
            for draft in drafts:
                if draft.marks is not None and draft.marks != request.marks:
                    status = OrchestrationRunStatus.FAILED
                    errors.append("marks_invariant_violation")
                    break
        if status == OrchestrationRunStatus.COMPLETED:
            approved_items = (
                [
                    draft.model_copy(update={"marks": request.marks})
                    if request.marks is not None
                    else draft
                    for draft in drafts
                ]
                if request.marks is not None
                else list(drafts)
            )

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

    eligible_for_meta = state.get("root_cause_eligible_tag_count")
    eligible_count_meta = (
        eligible_for_meta if isinstance(eligible_for_meta, int) else 0
    )

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
        metadata_json={
            "institution_id": scope.institution_id,
            "diagnostic_results": state.get("diagnostic_results") or [],
            "root_cause_results": state.get("root_cause_results") or [],
            "root_cause_not_applicable": (
                request.root_cause_enrichment_enabled()
                and eligible_count_meta == 0
                and len(state.get("root_cause_results") or []) == 0
            ),
        },
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
