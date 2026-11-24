from __future__ import annotations

from typing import Any

_FORBIDDEN_LOG_KEYS = frozenset({"display_name", "email", "phone", "address", "password"})


def redact_learner_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """D15-32: strip obvious PII keys from read models."""

    return {k: v for k, v in payload.items() if k not in _FORBIDDEN_LOG_KEYS}


def assert_no_cross_tenant(
    *,
    expected_organization_id: str,
    expected_institution_id: str,
    actual_organization_id: str,
    actual_institution_id: str,
) -> bool:
    return (
        expected_organization_id == actual_organization_id
        and expected_institution_id == actual_institution_id
    )