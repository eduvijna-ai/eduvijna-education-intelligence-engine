from __future__ import annotations

import pytest

from app.adapters.anythingllm.factory import build_anythingllm_adapter
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.http_adapter import HttpAnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterError, AdapterErrorCode
from app.core.config import Settings


def test_build_adapter_requires_explicit_fake_without_credentials() -> None:
    settings = Settings(anythingllm_base_url=None, anythingllm_api_key=None)
    with pytest.raises(AdapterError) as exc:
        build_anythingllm_adapter(settings, force_fake=False)
    assert exc.value.code == AdapterErrorCode.CONFIGURATION


def test_build_adapter_rejects_partial_credentials() -> None:
    with pytest.raises(AdapterError):
        build_anythingllm_adapter(
            Settings(anythingllm_base_url="http://anythingllm.test", anythingllm_api_key=None),
            force_fake=False,
        )
    with pytest.raises(AdapterError):
        build_anythingllm_adapter(
            Settings(anythingllm_base_url=None, anythingllm_api_key="secret"),
            force_fake=False,
        )


def test_build_adapter_explicit_fake_and_configured_http() -> None:
    assert isinstance(build_anythingllm_adapter(force_fake=True), FakeAnythingLLMAdapter)
    configured = build_anythingllm_adapter(
        Settings(anythingllm_base_url="http://anythingllm.test", anythingllm_api_key="secret"),
        force_fake=False,
    )
    assert isinstance(configured, HttpAnythingLLMAdapter)
