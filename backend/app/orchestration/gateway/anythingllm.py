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

_SUPPORTED_MODEL_SETTINGS = frozenset({"temperature", "top_p"})


class AnythingLLMGenerationGateway:
    """Production generation via AnythingLLM workspace chat API (D8-05 / D8-CR03)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
        workspace_slug: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._workspace_slug = workspace_slug
        self._history: list[GenerationResponse] = []

    def call_history(self) -> list[GenerationResponse]:
        return list(self._history)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _build_message(request: GenerationRequest) -> str:
        payload_json = json.dumps(request.user_payload, sort_keys=True, default=str)
        return (
            f"[EDUVIJNA_PROMPT_VERSION={request.prompt_version}]\n"
            f"[EDUVIJNA_OUTPUT_SCHEMA={request.output_schema_name}]\n"
            f"[INSTRUCTIONS]\n{request.system_prompt}\n"
            f"[STRUCTURED_PAYLOAD]\n{payload_json}\n"
            "Respond with a single JSON object only."
        )

    @staticmethod
    def _validate_model_settings(model_settings: dict[str, Any]) -> None:
        unsupported = set(model_settings) - _SUPPORTED_MODEL_SETTINGS
        if unsupported:
            raise GenerationGatewayError(
                "gateway_validation",
                f"Unsupported model settings: {sorted(unsupported)}",
                retryable=False,
            )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if request.model_settings:
            self._validate_model_settings(request.model_settings)
        workspace = request.workspace_slug or self._workspace_slug
        if not workspace:
            raise GenerationGatewayError(
                "gateway_configuration", "orchestration workspace slug is required", retryable=False
            )
        started = time.perf_counter()
        body: dict[str, Any] = {
            "message": self._build_message(request),
            "mode": "chat",
        }
        path = f"/api/v1/workspace/{workspace}/chat"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers=self._headers(),
                    json=body,
                )
        except httpx.TimeoutException:
            raise GenerationGatewayError(
                "gateway_timeout",
                "AnythingLLM chat timed out",
                retryable=True,
            ) from None
        except httpx.HTTPError as exc:
            logger.debug("AnythingLLM generation transport failure: %s", type(exc).__name__)
            raise GenerationGatewayError(
                "gateway_unavailable", "AnythingLLM transport error", retryable=True
            ) from exc

        if response.status_code in {401, 403}:
            raise GenerationGatewayError(
                "gateway_unauthorized",
                "AnythingLLM unauthorized",
                retryable=False,
                http_status=response.status_code,
            )
        if response.status_code >= 400:
            raise GenerationGatewayError(
                "gateway_unavailable",
                f"AnythingLLM HTTP {response.status_code}",
                retryable=response.status_code >= 500,
                http_status=response.status_code,
            )
        try:
            payload: dict[str, Any] = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise GenerationGatewayError(
                "gateway_invalid_json", "AnythingLLM response is not JSON"
            ) from exc
        if payload.get("error"):
            raise GenerationGatewayError(
                "gateway_unavailable",
                str(payload.get("error")),
                retryable=False,
            )
        text = str(payload.get("textResponse") or payload.get("response") or "").strip()
        if not text:
            raise GenerationGatewayError(
                "gateway_invalid_json", "AnythingLLM returned empty model content"
            )
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
            usage={
                "source": "anythingllm",
                "model_calls": 1,
                "tokens_unavailable": True,
            },
        )
        self._history.append(result)
        return result
