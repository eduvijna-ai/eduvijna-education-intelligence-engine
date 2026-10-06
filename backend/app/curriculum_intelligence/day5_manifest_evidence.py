"""Day 5 manifest evidence roles: required academic vs supplemental authority."""

from __future__ import annotations

from typing import Any, Literal

from app.curriculum_intelligence.source_domains import source_domain
from app.schemas.curriculum_intelligence import OfficialSourceManifestEntry

ManifestEvidenceRole = Literal["required_academic", "supplemental_authority"]

_SUPPLEMENTAL_DOCUMENT_TYPES = frozenset({"authority_directory"})


def manifest_source_snapshot(entry: OfficialSourceManifestEntry) -> dict[str, Any]:
    metadata = dict(entry.metadata_json or {})
    return {
        "source_type": entry.source_type,
        "metadata_json": {
            "document_type": entry.document_type,
            **metadata,
        },
    }


def manifest_evidence_role(entry: OfficialSourceManifestEntry) -> ManifestEvidenceRole:
    """Classify manifest entries for Day 5 official gates.

    Only ``authority_directory`` with a matching domain is supplemental. A
    syllabus, catalogue, or other academic document cannot bypass required
    applicability proof via ``governing_curriculum_membership: false``.
    """
    if entry.document_type in _SUPPLEMENTAL_DOCUMENT_TYPES:
        domain = source_domain(manifest_source_snapshot(entry))
        if domain != "authority_reference":
            raise ValueError(
                "authority_directory manifest entries must resolve to authority_reference domain"
            )
        return "supplemental_authority"
    return "required_academic"


def is_supplemental_authority_evidence(entry: OfficialSourceManifestEntry) -> bool:
    return manifest_evidence_role(entry) == "supplemental_authority"
