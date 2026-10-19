from __future__ import annotations

from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.diagnostic_routing import diagnostics_finished, pending_diagnostic_enrichment


def test_pending_diagnostic_enrichment_when_results_missing() -> None:
    request = OrchestrationRequest(
        idempotency_key="routing-key-001",
        retrieval_profile_version="default",
        metadata_json={"diagnostic_enrichment_enabled": True},
    )
    state = {
        "request": request.model_dump(mode="json"),
        "draft_items": [{"item_id": "item-a", "slot_index": 0}],
        "diagnostic_results": [],
        "diagnostic_validation": [],
    }
    assert pending_diagnostic_enrichment(state, request) is True
    assert diagnostics_finished(state, request) is False


def test_diagnostic_review_not_cleared_by_deterministic_human_approval() -> None:
    request = OrchestrationRequest(
        idempotency_key="routing-key-002",
        retrieval_profile_version="default",
        requested_count=1,
        metadata_json={"diagnostic_enrichment_enabled": True},
    )
    state = {
        "run_id": "run-1",
        "request": request.model_dump(mode="json"),
        "request_hash": request.request_hash(),
        "draft_items": [
            {
                "item_id": "item-a",
                "slot_index": 0,
                "stem_text": "Synthetic",
                "question_type": "single_choice",
                "options": [],
                "source_revision_ids": [],
            }
        ],
        "diagnostic_results": [
            {
                "item_id": "item-a",
                "aggregate_status": "review_required",
                "option_tags": [],
            }
        ],
        "diagnostic_validation": [
            {
                "item_id": "item-a",
                "review_required": True,
                "blocking": False,
                "repairable": False,
            }
        ],
        "deterministic_validation": [],
        "duplicate_validation": [],
        "human_approved": True,
        "diagnostic_human_approved": False,
        "repair_count_by_item": {},
        "errors": [],
        "warnings": [],
    }
    assert diagnostics_finished(state, request) is False
