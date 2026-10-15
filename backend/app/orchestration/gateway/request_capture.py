"""Test/verifier-only gateway wrapper recording generation requests at invoke time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.gateway.types import GenerationRequest, GenerationResponse


@dataclass(frozen=True, slots=True)
class CapturedGenerationRequest:
    role: GenerationNodeRole
    system_prompt: str
    user_payload: dict[str, Any]


class RequestCapturingGateway:
    """Delegates to an inner gateway while recording each ``generate()`` request."""

    def __init__(self, inner: GenerationGateway) -> None:
        self._inner: GenerationGateway = inner
        self._captured: list[CapturedGenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._captured.append(
            CapturedGenerationRequest(
                role=request.role,
                system_prompt=request.system_prompt,
                user_payload=dict(request.user_payload),
            )
        )
        return self._inner.generate(request)

    def call_history(self) -> list[GenerationResponse]:
        return self._inner.call_history()

    def captured_requests(self) -> list[CapturedGenerationRequest]:
        return list(self._captured)

    def captured_for_role(self, role: GenerationNodeRole) -> list[CapturedGenerationRequest]:
        return [entry for entry in self._captured if entry.role == role]
