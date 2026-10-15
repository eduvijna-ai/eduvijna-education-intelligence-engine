from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.orchestration.gateway.types import (
    GenerationGatewayError,
    GenerationRequest,
    GenerationResponse,
)

logger = logging.getLogger("eduvijna.orchestration.anythingllm")


class AnythingLLMGenerationGateway:
    """Production generation via AnythingLLM workspace chat API (D8-05)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        default_workspace: str = "default",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._default_workspace = default_workspace
        self._history: list[GenerationResponse] = []

    def call_history(self) -> list[GenerationResponse]:
        return list(self._history)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        workspace = request.workspace_slug or self._default_workspace
        started = time.perf_counter()
        body = {
            "message": json.dumps(request.user_payload, sort_keys=True, default=str),
            "mode": "chat",
            "systemPrompt": (
                f"{request.system_prompt}\n\n"
                f"Respond with JSON only for schema {request.output_schema_name}."
            ),
        }
        path = f"/api/v1/workspace/{workspace}/chat"
        last_error: GenerationGatewayError | None = None
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        f"{self._base_url}{path}",
                        headers=self._headers(),
                        json=body,
                    )
            except httpx.TimeoutException:
                last_error = GenerationGatewayError(
                    "gateway_timeout", "AnythingLLM chat timed out", retryable=True
                )
                if attempt < attempts - 1:
                    continue
                raise last_error from None
            except httpx.HTTPError as exc:
                last_error = GenerationGatewayError(
                    "gateway_unavailable", "AnythingLLM transport error", retryable=True
                )
                logger.debug("AnythingLLM generation transport failure: %s", type(exc).__name__)
                if attempt < attempts - 1:
                    continue
                raise last_error from exc

            if response.status_code in {401, 403}:
                raise GenerationGatewayError(
                    "gateway_unauthorized",
                    "AnythingLLM unauthorized",
                    retryable=False,
                    http_status=response.status_code,
                )
            if response.status_code >= 500:
                last_error = GenerationGatewayError(
                    "gateway_unavailable",
                    f"AnythingLLM server error {response.status_code}",
                    retryable=True,
                    http_status=response.status_code,
                )
                if attempt < attempts - 1:
                    continue
                raise last_error
            if response.status_code >= 400:
                raise GenerationGatewayError(
                    "gateway_unavailable",
                    f"AnythingLLM client error {response.status_code}",
                    retryable=False,
                    http_status=response.status_code,
                )
            try:
                payload: dict[str, Any] = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise GenerationGatewayError(
                    "gateway_invalid_json", "AnythingLLM response is not JSON"
                ) from exc
            text = str(payload.get("textResponse") or payload.get("response") or "")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise GenerationGatewayError(
                    "gateway_invalid_json", "Model response is not valid JSON"
                ) from exc
            if not isinstance(parsed, dict):
                raise GenerationGatewayError(
                    "gateway_invalid_json", "Model JSON root must be an object"
                )
            latency_ms = (time.perf_counter() - started) * 1000
            gateway_request_id = response.headers.get("x-request-id") or payload.get("id")
            result = GenerationResponse(
                parsed=parsed,
                raw_text=text,
                latency_ms=latency_ms,
                gateway_request_id=str(gateway_request_id) if gateway_request_id else None,
                usage={"source": "anythingllm"},
            )
            self._history.append(result)
            return result
        if last_error:
            raise last_error
        raise GenerationGatewayError("gateway_unavailable", "AnythingLLM request failed")
