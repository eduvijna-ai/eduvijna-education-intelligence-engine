"""Reasoning-demand metadata tags (D12-12) aligned with Day6 taxonomy keys."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.models import Question


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


def reasoning_profile_for_question(question: Question) -> ReasoningProfile:
    """D12-12: bind metadata from persisted Question (Day6 taxonomy keys)."""

    meta = question.metadata_json or {}
    cognitive = tuple(meta.get("cognitive_keys") or meta.get("cognitive_weights", {}).keys())
    competency = tuple(meta.get("competency_keys") or ())
    demand_raw = str(meta.get("reasoning_demand") or "multistep").lower()
    try:
        demand = ReasoningDemand(demand_raw)
    except ValueError:
        demand = ReasoningDemand.MULTISTEP
    return ReasoningProfile(
        demand=demand,
        competency_keys=competency or default_advanced_reasoning_profile().competency_keys,
        cognitive_keys=cognitive or default_advanced_reasoning_profile().cognitive_keys,
        source_neutral=not bool(meta.get("official_reference_item")),
    )