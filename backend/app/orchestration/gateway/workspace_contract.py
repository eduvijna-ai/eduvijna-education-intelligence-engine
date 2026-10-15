from __future__ import annotations

from typing import Any

import httpx

from app.orchestration.gateway.types import GenerationGatewayError


def verify_orchestration_workspace(
    *,
    base_url: str,
    api_key: str,
    workspace_slug: str,
    timeout_seconds: float = 10.0,
) -> None:
    """Fail closed when workspace has attached documents (untracked RAG injection risk)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    path = f"/api/v1/workspace/{workspace_slug}"
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(f"{base_url.rstrip('/')}{path}", headers=headers)
    except httpx.HTTPError as exc:
        raise GenerationGatewayError(
            "gateway_unavailable",
            f"Unable to verify orchestration workspace contract: {exc}",
            retryable=True,
        ) from exc
    if response.status_code in {401, 403}:
        raise GenerationGatewayError(
            "gateway_unauthorized",
            "AnythingLLM unauthorized during workspace contract check",
            retryable=False,
            http_status=response.status_code,
        )
    if response.status_code >= 400:
        raise GenerationGatewayError(
            "gateway_unavailable",
            f"Workspace contract check failed HTTP {response.status_code}",
            retryable=response.status_code >= 500,
            http_status=response.status_code,
        )
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise GenerationGatewayError(
            "gateway_invalid_json", "Workspace contract response is not JSON"
        ) from exc
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else payload
    documents = workspace.get("documents") if isinstance(workspace, dict) else None
    if documents is None and isinstance(workspace, dict):
        documents = workspace.get("documentCount")
    if isinstance(documents, list) and len(documents) > 0:
        raise GenerationGatewayError(
            "gateway_configuration",
            "Orchestration workspace must have zero attached documents",
            retryable=False,
        )
    if isinstance(documents, int) and documents > 0:
        raise GenerationGatewayError(
            "gateway_configuration",
            "Orchestration workspace must have zero attached documents",
            retryable=False,
        )
