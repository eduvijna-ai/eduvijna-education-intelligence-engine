from __future__ import annotations

from sqlalchemy.orm import Session

from app.cuet_clat.constants import PRIMARY_SOURCE_MANIFEST


def build_source_manifest() -> list[dict[str, str]]:
    """D13-02: primary-source manifest with URL/year/rights (no fabricated hashes)."""

    return [dict(row) for row in PRIMARY_SOURCE_MANIFEST]


def cuet_reference_evidence_ready(session: Session | None = None) -> bool:
    """D13-03: True only when curator-approved CUET 2026 bytes exist in Day3 workflow."""

    _ = session
    return False


def clat_official_evidence_ready(session: Session | None = None) -> bool:
    """D13-05: True only when Consortium 2027 sources are staged and reviewed."""

    _ = session
    return False


def build_source_registry_snapshot(session: Session | None = None) -> dict[str, object]:
    return {
        "manifest_entries": len(build_source_manifest()),
        "cuet_reference_curator_approved": cuet_reference_evidence_ready(session),
        "clat_official_curator_approved": clat_official_evidence_ready(session),
        "cuet_2027_official_verified": False,
        "manifest": build_source_manifest(),
    }