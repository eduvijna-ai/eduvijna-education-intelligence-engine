from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def record_diagnostic_audit_event(
    *,
    run_id: str,
    item_id: str,
    taxonomy_version: str,
    prompt_version: str | None,
    misconception_codes: list[str],
    issue_codes: list[str],
    status: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    event_id = str(uuid4())
    _ = {
        "event_id": event_id,
        "run_id": run_id,
        "item_id": item_id,
        "taxonomy_version": taxonomy_version,
        "prompt_version": prompt_version,
        "misconception_codes": misconception_codes,
        "issue_codes": issue_codes,
        "status": status,
        "recorded_at": datetime.now(UTC).isoformat(),
        "metadata": metadata or {},
    }
    return event_id
