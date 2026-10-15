from __future__ import annotations

from typing import Protocol

from app.orchestration.gateway.types import GenerationRequest, GenerationResponse


class GenerationGateway(Protocol):
    """Typed model-generation port; production uses AnythingLLM only (D8-04)."""

    def generate(self, request: GenerationRequest) -> GenerationResponse: ...

    def call_history(self) -> list[GenerationResponse]: ...
