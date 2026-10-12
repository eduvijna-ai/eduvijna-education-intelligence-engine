from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    version: str
    default_top_k: int
    score_threshold: float
    deduplicate: bool
    prefer_official_authority: bool
    max_context_characters: int
    max_context_items: int
    allowed_scopes: tuple[str, ...]
    rerank_hook: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "default_top_k": self.default_top_k,
            "score_threshold": self.score_threshold,
            "deduplicate": self.deduplicate,
            "prefer_official_authority": self.prefer_official_authority,
            "max_context_characters": self.max_context_characters,
            "max_context_items": self.max_context_items,
            "allowed_scopes": list(self.allowed_scopes),
            "rerank_hook": self.rerank_hook,
        }


DEFAULT_RETRIEVAL_PROFILE_VERSION = "ki-retrieval-v1"

_PROFILES: dict[str, RetrievalProfile] = {
    DEFAULT_RETRIEVAL_PROFILE_VERSION: RetrievalProfile(
        version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        default_top_k=5,
        score_threshold=0.0,
        deduplicate=True,
        prefer_official_authority=True,
        max_context_characters=6000,
        max_context_items=8,
        allowed_scopes=(
            "global_official",
            "organization",
            "institution",
            "teacher",
        ),
        rerank_hook=None,
    ),
    "ki-retrieval-v0": RetrievalProfile(
        version="ki-retrieval-v0",
        default_top_k=3,
        score_threshold=0.0,
        deduplicate=False,
        prefer_official_authority=False,
        max_context_characters=4000,
        max_context_items=5,
        allowed_scopes=(
            "global_official",
            "organization",
            "institution",
            "teacher",
        ),
        rerank_hook=None,
    ),
}


class RetrievalProfileError(ValueError):
    pass


def load_retrieval_profile(version: str) -> RetrievalProfile:
    profile = _PROFILES.get(version)
    if profile is None:
        raise RetrievalProfileError(f"Unknown retrieval profile version: {version}")
    return profile


def list_retrieval_profile_versions() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES.keys()))
