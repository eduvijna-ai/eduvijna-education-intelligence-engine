from __future__ import annotations

import os

from app.adapters.anythingllm.types import AdapterError, AdapterErrorCode
from app.core.config import Settings, get_settings
from app.orchestration.exceptions import OrchestrationConfigurationError
from app.orchestration.gateway.anythingllm import AnythingLLMGenerationGateway
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.protocol import GenerationGateway


def build_generation_gateway(
    settings: Settings | None = None,
    *,
    force_fake: bool | None = None,
) -> GenerationGateway:
    resolved = settings or get_settings()
    use_fake = force_fake
    if use_fake is None:
        env_flag = os.environ.get("EDUVIJNA_ORCHESTRATION_USE_FAKE", "").strip().lower()
        use_fake = env_flag in {"1", "true", "yes"}
    if use_fake:
        return FakeGenerationGateway()

    base_url = (resolved.anythingllm_base_url or "").strip()
    api_key = (resolved.anythingllm_api_key or "").strip()
    workspace = (getattr(resolved, "anythingllm_orchestration_workspace", None) or "").strip()
    if not base_url or not api_key or not workspace:
        raise OrchestrationConfigurationError(
            "AnythingLLM orchestration gateway requires base URL, API key, and "
            "ANYTHINGLLM_ORCHESTRATION_WORKSPACE"
        )
    timeout = float(os.environ.get("ANYTHINGLLM_GENERATION_TIMEOUT_SECONDS", "30"))
    return AnythingLLMGenerationGateway(
        base_url,
        api_key,
        timeout_seconds=timeout,
        workspace_slug=workspace,
    )


def configuration_error_from_adapter(exc: AdapterError) -> OrchestrationConfigurationError:
    if exc.code == AdapterErrorCode.CONFIGURATION:
        return OrchestrationConfigurationError(exc.message)
    raise exc
