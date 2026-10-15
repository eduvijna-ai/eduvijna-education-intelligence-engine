from __future__ import annotations

import os

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.http_adapter import HttpAnythingLLMAdapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterError, AdapterErrorCode
from app.core.config import Settings, get_settings


def build_anythingllm_adapter(
    settings: Settings | None = None,
    *,
    force_fake: bool | None = None,
) -> AnythingLLMAdapter:
    resolved = settings or get_settings()
    use_fake = force_fake
    if use_fake is None:
        env_flag = os.environ.get("EDUVIJNA_KNOWLEDGE_USE_FAKE", "").strip().lower()
        use_fake = env_flag in {"1", "true", "yes"}
    if use_fake:
        return FakeAnythingLLMAdapter()
    base_url = (resolved.anythingllm_base_url or "").strip()
    api_key = (resolved.anythingllm_api_key or "").strip()
    if not base_url or not api_key:
        raise AdapterError(
            AdapterErrorCode.CONFIGURATION,
            "AnythingLLM gateway credentials are not configured",
            retryable=False,
        )
    return HttpAnythingLLMAdapter(
        base_url,
        api_key,
        timeout_seconds=float(os.environ.get("ANYTHINGLLM_TIMEOUT_SECONDS", "15")),
        max_retries=int(os.environ.get("ANYTHINGLLM_MAX_RETRIES", "2")),
    )
