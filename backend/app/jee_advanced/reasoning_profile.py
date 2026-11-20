"""Reasoning-demand metadata tags (D12-12) aligned with Day6 taxonomy keys."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReasoningDemand(StrEnum):
    PROCEDURAL = "procedural"
    CONCEPTUAL = "conceptual"
    MULTISTEP = "multistep"
    HOTS = "hots"


@dataclass(frozen=True, slots=True)
class ReasoningProfile:
    demand: ReasoningDemand
    competency_keys: tuple[str, ...]
    cognitive_keys: tuple[str, ...]
    source_neutral: bool = True


def default_advanced_reasoning_profile() -> ReasoningProfile:
    """Source-neutral demonstration profile; not an invented JAB chapter quota."""

    return ReasoningProfile(
        demand=ReasoningDemand.MULTISTEP,
        competency_keys=("problem_solving", "analysis"),
        cognitive_keys=("apply", "analyze"),
        source_neutral=True,
    )