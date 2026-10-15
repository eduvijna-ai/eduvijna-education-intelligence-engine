from __future__ import annotations

from typing import Any

import httpx

from app.orchestration.gateway.types import GenerationGatewayError

ORCHESTRATION_WORKSPACE_PROMPT_MARKER = "EDUVIJNA_ORCHESTRATION_V1"


def _workspace_record(payload: dict[str, Any], workspace_slug: str) -> dict[str, Any]:
    raw = payload.get("workspace")
    if isinstance(raw, list):
        if len(raw) != 1 or not isinstance(raw[0], dict):
            raise GenerationGatewayError(
                "gateway_configuration",
                "Unable to verify dedicated orchestration workspace shape",
                retryable=False,
            )
        workspace = raw[0]
    elif isinstance(raw, dict):
        workspace = raw
    else:
        raise GenerationGatewayError(
            "gateway_configuration",
            "AnythingLLM workspace response did not expose a verifiable workspace",
            retryable=False,
        )
    if str(workspace.get("slug") or "").strip() != workspace_slug:
        raise GenerationGatewayError(
            "gateway_configuration",
            "AnythingLLM workspace identity did not match configured orchestration workspace",
            retryable=False,
        )
    return workspace


def verify_orchestration_workspace(
    *,
    base_url: str,
    api_key: str,
    workspace_slug: str,
    timeout_seconds: float = 10.0,
) -> None:
    """Fail closed unless the dedicated workspace proves zero documents + trusted guard."""
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

    workspace = _workspace_record(payload, workspace_slug)
    documents = workspace.get("documents")
    document_count = workspace.get("documentCount")
    zero_documents_verified = (
        isinstance(documents, list) and len(documents) == 0
    ) or (
        isinstance(document_count, int)
        and not isinstance(document_count, bool)
        and document_count == 0
    )
    if not zero_documents_verified:
        raise GenerationGatewayError(
            "gateway_configuration",
            "Orchestration workspace must prove zero attached documents",
            retryable=False,
        )

    system_prompt = workspace.get("openAiPrompt")
    if (
        not isinstance(system_prompt, str)
        or ORCHESTRATION_WORKSPACE_PROMPT_MARKER not in system_prompt
    ):
        raise GenerationGatewayError(
            "gateway_configuration",
            "Orchestration workspace trusted system-prompt marker is missing",
            retryable=False,
        )
