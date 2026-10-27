from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaperExecutionContext:
    """Trusted tenant/actor for paper distribution persistence and Day6 binding."""

    institution_id: str | None = None
    actor_id: str | None = None
    board_code: str | None = None
