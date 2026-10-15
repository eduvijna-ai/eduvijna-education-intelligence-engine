from __future__ import annotations

import time
from typing import Any

from langgraph.types import interrupt

from app.orchestration.contracts import DraftQuestionItem
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.nodes._helpers import audit_node, next_attempt, timed_update
from app.orchestration.state import OrchestrationGraphState

_HUMAN_IMMUTABLE_PATCH_KEYS = frozenset(
    {
        "item_id",
        "slot_index",
        "source_revision_ids",
        "learning_outcome_ids",
        "competency_codes",
    }
)


def _build_interrupt_payload(state: OrchestrationGraphState) -> dict[str, Any]:
    drafts = state.get("draft_items") or []
    item_ids = [str(item.get("item_id")) for item in drafts if item.get("item_id")]
    revision_ids: list[str] = []
    for item in drafts:
        for revision_id in item.get("source_revision_ids") or []:
            revision_ids.append(str(revision_id))
    return {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "item_ids": item_ids,
        "repair_count_by_item": state.get("repair_count_by_item") or {},
        "deterministic_validation": state.get("deterministic_validation") or [],
        "review_verdicts": state.get("review_verdicts") or [],
        "source_revision_ids": sorted(set(revision_ids)),
        "errors": state.get("errors") or [],
        "warnings": state.get("warnings") or [],
    }


def human_gate_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "human_gate")
    payload = _build_interrupt_payload(state)
    decision_raw = interrupt(payload)
    decision = HumanResumeDecision.model_validate(decision_raw)
    audit_id = audit_node(
        deps,
        state,
        "human_gate",
        decision.action,
        attempt=attempt,
        payload=decision.model_dump(mode="json"),
    )
    if decision.action == "reject":
        return timed_update(
            state,
            "human_gate",
            started,
            {
                "human_decision": decision.model_dump(mode="json"),
                "human_revalidate": False,
                "status": OrchestrationRunStatus.FAILED.value,
                "errors": list(state.get("errors") or []) + ["human_rejected"],
                "pipeline_halt": True,
                "audit_refs": [audit_id],
            },
            attempt_map=attempt_map,
        )
    if decision.action == "edit":
        drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
        patched: list[dict[str, Any]] = []
        for draft in drafts:
            patch = decision.item_patches.get(draft.item_id)
            if patch:
                forbidden = [key for key in patch if key in _HUMAN_IMMUTABLE_PATCH_KEYS]
                if forbidden:
                    return timed_update(
                        state,
                        "human_gate",
                        started,
                        {
                            "human_decision": decision.model_dump(mode="json"),
                            "status": OrchestrationRunStatus.FAILED.value,
                            "errors": list(state.get("errors") or [])
                            + ["human_edit_provenance_forbidden"],
                            "pipeline_halt": True,
                            "audit_refs": [audit_id],
                        },
                        attempt_map=attempt_map,
                    )
                updated = DraftQuestionItem.model_validate(
                    draft.model_copy(update=patch).model_dump(mode="json")
                )
                patched.append(updated.model_dump(mode="json"))
            else:
                patched.append(draft.model_dump(mode="json"))
        return timed_update(
            state,
            "human_gate",
            started,
            {
                "human_decision": decision.model_dump(mode="json"),
                "draft_items": patched,
                "human_revalidate": True,
                "human_approved": False,
                "status": OrchestrationRunStatus.REVIEWING.value,
                "interrupt_payload": payload,
                "audit_refs": [audit_id],
            },
            attempt_map=attempt_map,
        )
    return timed_update(
        state,
        "human_gate",
        started,
        {
            "human_decision": decision.model_dump(mode="json"),
            "human_approved": True,
            "human_revalidate": False,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "interrupt_payload": payload,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
