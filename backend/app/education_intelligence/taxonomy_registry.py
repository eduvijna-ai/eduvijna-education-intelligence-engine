from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import TaxonomyRegistryEntry

V1_TAXONOMY_VERSION = "cognitive-competency-v1.0"

V1_COGNITIVE_LEVELS: dict[str, dict[str, Any]] = {
    "remember": {"label": "Remember", "order": 1, "aliases": ["recall", "knowledge_recall"]},
    "understand": {"label": "Understand", "order": 2, "aliases": ["comprehension"]},
    "apply": {"label": "Apply", "order": 3, "aliases": ["application"]},
    "analyze": {"label": "Analyze", "order": 4, "aliases": ["analysis"]},
    "evaluate": {"label": "Evaluate", "order": 5, "aliases": ["evaluation"]},
}

V1_COMPETENCIES: dict[str, dict[str, Any]] = {
    "knowledge": {"label": "Knowledge", "aliases": []},
    "conceptual_understanding": {
        "label": "Conceptual Understanding",
        "aliases": ["conceptual understanding"],
    },
    "application": {"label": "Application", "aliases": []},
    "analysis": {"label": "Analysis", "aliases": []},
    "problem_solving": {"label": "Problem Solving", "aliases": ["problem-solving"]},
    "hots": {"label": "HOTS", "aliases": ["higher_order_thinking"]},
}

COGNITIVE_PROGRESSION_ORDER = [
    "remember",
    "understand",
    "apply",
    "analyze",
    "evaluate",
]


@dataclass
class TaxonomyRegistry:
    version: str = V1_TAXONOMY_VERSION
    cognitive: dict[str, dict[str, Any]] = field(default_factory=lambda: dict(V1_COGNITIVE_LEVELS))
    competencies: dict[str, dict[str, Any]] = field(default_factory=lambda: dict(V1_COMPETENCIES))

    def resolve_cognitive(self, raw: str) -> tuple[str | None, bool]:
        key = raw.strip().lower().replace(" ", "_").replace("-", "_")
        if key in self.cognitive:
            return key, False
        for code, meta in self.cognitive.items():
            if key == meta["label"].lower().replace(" ", "_"):
                return code, False
            for alias in meta.get("aliases", []):
                if key == alias.lower().replace(" ", "_"):
                    return code, True
        return None, False

    def resolve_competency(self, raw: str) -> tuple[str | None, bool]:
        key = raw.strip().lower().replace(" ", "_").replace("-", "_")
        if key in self.competencies:
            return key, False
        for code, meta in self.competencies.items():
            if key == meta["label"].lower().replace(" ", "_"):
                return code, False
            for alias in meta.get("aliases", []):
                if key == alias.lower().replace(" ", "_"):
                    return code, True
        return None, False

    def cognitive_order_index(self, code: str) -> int | None:
        meta = self.cognitive.get(code)
        if not meta:
            return None
        return int(meta["order"])


def seed_taxonomy_registry(session: Session) -> TaxonomyRegistry:
    """Idempotent reload of v1 taxonomy into persistence."""
    existing = session.scalar(
        select(TaxonomyRegistryEntry).where(
            TaxonomyRegistryEntry.registry_key == "v1",
            TaxonomyRegistryEntry.version == V1_TAXONOMY_VERSION,
            TaxonomyRegistryEntry.status == "active",
        )
    )
    payload = {
        "cognitive": V1_COGNITIVE_LEVELS,
        "competencies": V1_COMPETENCIES,
    }
    if existing is None:
        session.add(
            TaxonomyRegistryEntry(
                registry_key="v1",
                version=V1_TAXONOMY_VERSION,
                status="active",
                payload_json=payload,
            )
        )
        session.flush()
    elif existing.payload_json != payload:
        existing.status = "superseded"
        session.add(
            TaxonomyRegistryEntry(
                registry_key="v1",
                version=V1_TAXONOMY_VERSION,
                status="active",
                payload_json=payload,
            )
        )
        session.flush()
    return TaxonomyRegistry()


def load_taxonomy_registry(
    session: Session | None, *, version: str | None = None
) -> TaxonomyRegistry:
    if session is None:
        return TaxonomyRegistry()
    if version:
        row = session.scalar(
            select(TaxonomyRegistryEntry).where(TaxonomyRegistryEntry.version == version)
        )
        if row is None:
            return TaxonomyRegistry(version=version)
        return TaxonomyRegistry(
            version=row.version,
            cognitive=row.payload_json.get("cognitive", V1_COGNITIVE_LEVELS),
            competencies=row.payload_json.get("competencies", V1_COMPETENCIES),
        )
    row = session.scalar(
        select(TaxonomyRegistryEntry)
        .where(TaxonomyRegistryEntry.registry_key == "v1")
        .order_by(TaxonomyRegistryEntry.created_at.desc())
        .limit(1)
    )
    if row is None:
        return seed_taxonomy_registry(session)
    return TaxonomyRegistry(
        version=row.version,
        cognitive=row.payload_json.get("cognitive", V1_COGNITIVE_LEVELS),
        competencies=row.payload_json.get("competencies", V1_COMPETENCIES),
    )
