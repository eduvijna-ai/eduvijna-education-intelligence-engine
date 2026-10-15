from __future__ import annotations

from typing import Any

from app.orchestration.nodes._helpers import audit_node
from app.orchestration.state import OrchestrationGraphState


def persist_diagnostic_item_audit(
    deps: Any,
    state: OrchestrationGraphState,
    *,
    item_id: str,
    attempt: int,
    status: str,
    taxonomy_version: str,
    prompt_version: str | None,
    misconception_codes: list[str],
    source_revision_ids: list[str],
    issue_codes: list[str],
    scope_metadata: dict[str, Any],
    repair_transition: str | None = None,
) -> str:
    payload = {
        "diagnostic": True,
        "item_id": item_id,
        "taxonomy_version": taxonomy_version,
        "misconception_codes": misconception_codes,
        "scope": scope_metadata,
        "repair_transition": repair_transition,
    }
    return audit_node(
        deps,
        state,
        "diagnostic_item",
        status,
        attempt=attempt,
        prompt_version=prompt_version,
        source_revision_ids=source_revision_ids,
        issue_codes=issue_codes,
        payload=payload,
    )
