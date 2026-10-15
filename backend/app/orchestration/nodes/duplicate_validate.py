from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import DraftQuestionItem
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.duplicate import validate_duplicates
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, next_attempt, timed_update
from app.orchestration.state import OrchestrationGraphState


def duplicate_validate_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "duplicate_validate")
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    summaries = [summary.model_dump(mode="json") for summary in validate_duplicates(drafts)]
    duplicate_hits = [s for s in summaries if s.get("is_duplicate")]
    audit_id = audit_node(
        deps,
        state,
        "duplicate_validate",
        "ok",
        attempt=attempt,
        issue_codes=["duplicate_content"] if duplicate_hits else [],
    )
    return timed_update(
        state,
        "duplicate_validate",
        started,
        {
            "duplicate_validation": summaries,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
