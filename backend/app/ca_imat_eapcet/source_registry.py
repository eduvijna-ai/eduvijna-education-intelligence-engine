from __future__ import annotations

from sqlalchemy.orm import Session

from app.ca_imat_eapcet.constants import PRIMARY_SOURCE_MANIFEST


def build_source_manifest() -> list[dict[str, str]]:
    return [dict(row) for row in PRIMARY_SOURCE_MANIFEST]


def ca_icai_evidence_ready(session: Session | None = None) -> bool:
    """Fail closed until curator-approved ICAI bytes exist (Day3 full authority chain)."""

    _ = session
    return False


def imat_decree_evidence_ready(session: Session | None = None) -> bool:
    _ = session
    return False


def eapcet_official_evidence_ready(session: Session | None = None) -> bool:
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
        "evaluation_mode": "fail_closed_pending_curator_bytes",
        "manifest": manifest,
    }