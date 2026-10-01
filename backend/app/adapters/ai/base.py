from __future__ import annotations

from typing import Protocol


class AIProvider(Protocol):
    async def health(self) -> bool: ...

    async def generate(self, prompt: str) -> str: ...
