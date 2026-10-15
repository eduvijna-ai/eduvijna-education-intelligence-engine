from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.orchestration.enums import GenerationNodeRole


@dataclass(frozen=True, slots=True)
class GenerationCallContext:
    run_id: str
    item_id: str | None
    role: GenerationNodeRole
    prompt_version: str
    scenario: str
    input_hash: str


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    role: GenerationNodeRole
    prompt_version: str
    system_prompt: str
    user_payload: dict[str, Any]
    output_schema_name: str
    scenario: str = "clean_pass"
    workspace_slug: str | None = None
    model_settings: dict[str, Any] = field(default_factory=dict)
    chat_session_id: str | None = None
    chat_reset: bool = False


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    parsed: dict[str, Any]
    raw_text: str
    latency_ms: float
    gateway_request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    call_context: GenerationCallContext | None = None


class GenerationGatewayError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status
