from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ca_imat_eapcet.constants import PRIMARY_SOURCE_MANIFEST
from app.models.enums import SourceRevisionStatus
from app.models.source import Source, SourceRevision


def build_source_manifest() -> list[dict[str, str]]:
    return [dict(row) for row in PRIMARY_SOURCE_MANIFEST]


def _approved_revision_for_exam(session: Session | None, *, exam_key: str) -> bool:
    if session is None:
        return False
    stmt = (
        select(SourceRevision)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(SourceRevision.status == SourceRevisionStatus.ACTIVE.value)
    )
    for rev in session.scalars(stmt).all():
        meta = dict(rev.source.metadata_json or {}) if rev.source else {}
        src_meta = dict(rev.extraction_metadata_json or {})
        combined = {**meta, **src_meta}
        if combined.get("d14_exam_family") == exam_key and rev.validated_checksum:
            return True
    return False


def ca_icai_evidence_ready(session: Session | None = None) -> bool:
    return _approved_revision_for_exam(session, exam_key="ca_foundation")


def imat_decree_evidence_ready(session: Session | None = None) -> bool:
    return _approved_revision_for_exam(session, exam_key="imat")


def eapcet_official_evidence_ready(session: Session | None = None) -> bool:
    return _approved_revision_for_exam(session, exam_key="tg_eapcet")


def build_source_registry_snapshot(session: Session | None = None) -> dict[str, object]:
    manifest = build_source_manifest()
    discovery_only = sum(1 for row in manifest if row.get("discovery_only") == "true")
    ca_ready = ca_icai_evidence_ready(session)
    imat_ready = imat_decree_evidence_ready(session)
    eapcet_ready = eapcet_official_evidence_ready(session)
    return {
        "manifest_entries": len(manifest),
        "discovery_mirror_entries": discovery_only,
        "ca_icai_curator_approved": ca_ready,
        "imat_decree_curator_approved": imat_ready,
        "eapcet_official_curator_approved": eapcet_ready,
        "official_intake_live": False,
        "evaluation_mode": "read_only_day3_active_revision_scan",
        "manifest": manifest,
    }