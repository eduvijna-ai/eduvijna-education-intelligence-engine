from __future__ import annotations

from sqlalchemy.orm import Session

from app.ca_imat_eapcet.constants import PRIMARY_SOURCE_MANIFEST


def build_source_manifest() -> list[dict[str, str]]:
    """D14-02: primary authority manifest with locator, version, rights (no fabricated hashes)."""

    return [dict(row) for row in PRIMARY_SOURCE_MANIFEST]


def ca_icai_evidence_ready(session: Session | None = None) -> bool:
    """D14-03: True only when ICAI session bytes are curator-approved in Day3 workflow."""

    _ = session
    return False


def imat_decree_evidence_ready(session: Session | None = None) -> bool:
    """D14-03: True only when MUR D.M.1005 and annexes are staged with SHA-256."""

    _ = session
    return False


def eapcet_official_evidence_ready(session: Session | None = None) -> bool:
    """D14-03: True only when TGCHE originals are attested (not discovery mirror alone)."""

    _ = session
    return False


def build_source_registry_snapshot(session: Session | None = None) -> dict[str, object]:
    manifest = build_source_manifest()
    discovery_only = sum(1 for row in manifest if row.get("discovery_only") == "true")
    return {
        "manifest_entries": len(manifest),
        "discovery_mirror_entries": discovery_only,
        "ca_icai_curator_approved": ca_icai_evidence_ready(session),
        "imat_decree_curator_approved": imat_decree_evidence_ready(session),
        "eapcet_official_curator_approved": eapcet_official_evidence_ready(session),
        "official_intake_live": False,
        "manifest": manifest,
    }