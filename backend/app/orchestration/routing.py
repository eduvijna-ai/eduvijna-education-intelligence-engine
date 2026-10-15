from __future__ import annotations

from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.state import OrchestrationGraphState


def pipeline_halted(state: OrchestrationGraphState) -> bool:
    if state.get("pipeline_halt"):
        return True
    if state.get("status") == OrchestrationRunStatus.FAILED.value:
        return True
    errors = state.get("errors") or []
    return bool(errors)


def route_after_scope(state: OrchestrationGraphState) -> str:
    if pipeline_halted(state):
        return "whole_output"
    scope = state.get("resolved_scope") or {}
    if scope.get("scope_errors"):
        return "whole_output"
    return "resolve_context"


def route_after_fallible(state: OrchestrationGraphState) -> str:
    if pipeline_halted(state):
        return "whole_output"
    return "continue"


def route_after_validation(state: OrchestrationGraphState) -> str:
    if pipeline_halted(state):
        return "whole_output"
    request = OrchestrationRequest.model_validate(state["request"])
    deterministic = state.get("deterministic_validation") or []
    duplicate = state.get("duplicate_validation") or []
    repair_counts = state.get("repair_count_by_item") or {}
    max_repairs = request.effective_max_repairs()

    if any(item.get("is_duplicate") for item in duplicate):
        return "whole_output"

    blocking = any(item.get("blocking") for item in deterministic)
    repairable = any(item.get("repairable") for item in deterministic)
    review_required = any(item.get("review_required") for item in deterministic)

    if blocking and not repairable:
        return "whole_output"

    if repairable:
        for summary in deterministic:
            if not summary.get("repairable"):
                continue
            item_id = str(summary.get("item_id"))
            if repair_counts.get(item_id, 0) < max_repairs:
                return "repair"
        if review_required or any(
            repair_counts.get(str(summary.get("item_id")), 0) >= max_repairs
            for summary in deterministic
            if summary.get("repairable")
        ):
            return "human_gate"
        return "whole_output"

    if review_required:
        return "human_gate"

    return "diagnostic_enrich"


def route_after_diagnostic(state: OrchestrationGraphState) -> str:
    if pipeline_halted(state):
        return "whole_output"
    request = OrchestrationRequest.model_validate(state["request"])
    if not request.diagnostic_enrichment_enabled():
        return "whole_output"

    diagnostic = state.get("diagnostic_validation") or []
    repair_counts = state.get("repair_count_by_item") or {}
    max_repairs = request.effective_max_repairs()

    blocking = any(item.get("blocking") for item in diagnostic)
    repairable = any(item.get("repairable") for item in diagnostic)
    review_required = any(item.get("review_required") for item in diagnostic)

    if blocking and not repairable:
        return "whole_output"

    if repairable:
        for summary in diagnostic:
            if not summary.get("repairable"):
                continue
            item_id = str(summary.get("item_id"))
            if repair_counts.get(item_id, 0) < max_repairs:
                return "repair"
        if review_required or any(
            repair_counts.get(str(summary.get("item_id")), 0) >= max_repairs
            for summary in diagnostic
            if summary.get("repairable")
        ):
            return "human_gate"
        return "whole_output"

    if review_required:
        return "human_gate"

    return "whole_output"


def route_after_human(state: OrchestrationGraphState) -> str:
    if pipeline_halted(state):
        return "whole_output"
    decision = state.get("human_decision") or {}
    if state.get("human_revalidate") and decision.get("action") == "edit":
        return "deterministic_validate"
    return "whole_output"
