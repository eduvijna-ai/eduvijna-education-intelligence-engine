from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.root_cause_intelligence.enums import DEFAULT_ROOT_CAUSE_MAPPING_VERSION


class MisconceptionConceptMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    misconception_code: str
    version: str
    candidate_concept_codes: list[str] = Field(default_factory=list)
    mechanism_notes: str | None = None
    source_revision_ids: list[str] = Field(default_factory=list)
    synthetic: bool = False


class RootCauseMappingRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    mappings: list[MisconceptionConceptMapping]

    def resolve(self, misconception_code: str) -> MisconceptionConceptMapping | None:
        for entry in self.mappings:
            if entry.misconception_code == misconception_code:
                return entry
        return None


@lru_cache(maxsize=4)
def load_root_cause_mapping(
    version: str = DEFAULT_ROOT_CAUSE_MAPPING_VERSION,
) -> RootCauseMappingRegistry:
    path = Path(__file__).resolve().parent / "data" / "root_cause_mapping_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != version:
        raise ValueError(f"unsupported mapping version: {version}")
    return RootCauseMappingRegistry.model_validate(payload)
