from __future__ import annotations

import os

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.http_adapter import HttpAnythingLLMAdapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
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
    if use_fake or not (resolved.anythingllm_base_url and resolved.anythingllm_api_key):
        return FakeAnythingLLMAdapter()
    return HttpAnythingLLMAdapter(
        resolved.anythingllm_base_url or "",
        resolved.anythingllm_api_key or "",
        timeout_seconds=float(os.environ.get("ANYTHINGLLM_TIMEOUT_SECONDS", "15")),
        max_retries=int(os.environ.get("ANYTHINGLLM_MAX_RETRIES", "2")),
    )
