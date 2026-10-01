from __future__ import annotations

from typing import Protocol


class KnowledgeProvider(Protocol):
    async def health(self) -> bool: ...

    async def retrieve(self, query: str, *, limit: int = 10) -> list[str]: ...

    async def embed(self, text: str) -> list[float]: ...
