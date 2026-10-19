from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.diagnostic_intelligence.contracts import MisconceptionDefinition, MisconceptionTaxonomy
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, MisconceptionStatus


class TaxonomyRegistryError(ValueError):
    pass


_DATA_DIR = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=8)
def load_taxonomy(version: str = DEFAULT_TAXONOMY_VERSION) -> MisconceptionTaxonomy:
    if version == DEFAULT_TAXONOMY_VERSION:
        path = _DATA_DIR / "misconception_taxonomy_v1.json"
    else:
        raise TaxonomyRegistryError(f"Unknown taxonomy version: {version}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    taxonomy = MisconceptionTaxonomy.model_validate(raw)
    if taxonomy.version != version:
        raise TaxonomyRegistryError(
            f"Taxonomy file version mismatch: expected {version}, got {taxonomy.version}"
        )
    codes: set[str] = set()
    for entry in taxonomy.misconceptions:
        if entry.misconception_code in codes:
            raise TaxonomyRegistryError(f"Duplicate misconception code: {entry.misconception_code}")
        codes.add(entry.misconception_code)
    return taxonomy


def resolve_misconception(
    code: str, *, taxonomy_version: str = DEFAULT_TAXONOMY_VERSION
) -> MisconceptionDefinition | None:
    taxonomy = load_taxonomy(taxonomy_version)
    for entry in taxonomy.misconceptions:
        if entry.misconception_code == code:
            return entry
    return None


def active_misconceptions(
    *, taxonomy_version: str = DEFAULT_TAXONOMY_VERSION
) -> list[MisconceptionDefinition]:
    taxonomy = load_taxonomy(taxonomy_version)
    return [m for m in taxonomy.misconceptions if m.status == MisconceptionStatus.ACTIVE]
