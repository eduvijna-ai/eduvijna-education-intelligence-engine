from __future__ import annotations

import httpx


class AnythingLLMProvider:
    def __init__(self, base_url: str | None, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def health(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/ping")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def generate(self, prompt: str) -> str:
        raise NotImplementedError("AnythingLLM generation is implemented in the Knowledge Intelligence day")

    async def retrieve(self, query: str, *, limit: int = 10) -> list[str]:
        raise NotImplementedError("AnythingLLM retrieval is implemented in the Knowledge Intelligence day")

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Embedding integration is implemented in the Knowledge Intelligence day")
