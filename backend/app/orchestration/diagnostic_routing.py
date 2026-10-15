from __future__ import annotations

from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.state import OrchestrationGraphState


def diagnostics_finished(state: OrchestrationGraphState, request: OrchestrationRequest) -> bool:
    if not request.diagnostic_enrichment_enabled():
        return True
    drafts = state.get("draft_items") or []
    if not drafts:
        return False
    results = {
        str(entry.get("item_id")): entry for entry in (state.get("diagnostic_results") or [])
    }
    for draft in drafts:
        item_id = str(draft.get("item_id"))
        if item_id not in results:
            return False
    diagnostic = state.get("diagnostic_validation") or []
    if any(item.get("blocking") or item.get("repairable") for item in diagnostic):
        return False
    if any(item.get("review_required") for item in diagnostic):
        return bool(state.get("diagnostic_human_approved"))
    return True


def pending_diagnostic_enrichment(
    state: OrchestrationGraphState, request: OrchestrationRequest
) -> bool:
    return request.diagnostic_enrichment_enabled() and not diagnostics_finished(state, request)
