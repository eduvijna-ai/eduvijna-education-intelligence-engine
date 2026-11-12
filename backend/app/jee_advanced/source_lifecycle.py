from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import JEE_ADVANCED_AUTHORITY
from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    apply_runtime_slot_evidence,
    reference_evidence_ready,
)
from app.models import Source, SourceRevision
from app.models.enums import SourceRevisionStatus, SourceTrustTier, SourceType
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService


def _find_slot_source(session: Session, slot_id: str) -> Source | None:
    candidates = session.scalars(
        select(Source).where(Source.board_or_exam == "jee_advanced")
    ).all()
    for source in candidates:
        if source.metadata_json.get("slot_id") == slot_id:
            return source
    return None


def register_discovery_sources(session: Session) -> list[str]:
    """D12-02/03: Stage official discovery metadata via Day3; never fabricate approval."""

    service = SourceIntelligenceService(session)
    registered: list[str] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        existing = _find_slot_source(session, slot.slot_id)
        if existing is not None:
            registered.append(str(existing.id))
            continue
        source_type = (
            SourceType.OFFICIAL_PAPER
            if "paper" in slot.slot_id and "key" not in slot.slot_id
            else SourceType.ANSWER_KEY
            if "key" in slot.slot_id
            else SourceType.OFFICIAL_SYLLABUS
            if "syllabus" in slot.slot_id
            else SourceType.OFFICIAL_EXAM_BULLETIN
        )
        payload = SourceRegistrationInput(
            source_type=source_type,
            title=slot.title,
            url=slot.discovery_url,
            authority=JEE_ADVANCED_AUTHORITY,
            country="IN",
            board_or_exam="jee_advanced",
            academic_year="2026",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json={
                "slot_id": slot.slot_id,
                "jee_advanced_slot": True,
                "ingest_status": "SOURCE_PENDING",
            },
        )
        source = service.register_source(payload)
        session.flush()
        registered.append(str(source.id))
    session.commit()
    return registered


def sync_slot_evidence_from_session(session: Session) -> dict[str, Any]:
    """Read persisted revisions; record SHA only from stored bytes, not fabricated."""

    evidence: dict[str, dict[str, str | None]] = {}
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        source = _find_slot_source(session, slot.slot_id)
        if source is None:
            evidence[slot.slot_id] = {
                "source_id": None,
                "staged_sha256": None,
                "approved_revision_id": None,
            }
            continue

        revision = session.scalar(
            select(SourceRevision)
            .where(
                SourceRevision.source_id == source.id,
                SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
            )
            .order_by(SourceRevision.revision_number.desc())
        )
        approved_id = str(revision.id) if revision is not None else None
        evidence[slot.slot_id] = {
            "source_id": str(source.id),
            "staged_sha256": revision.checksum if revision else None,
            "approved_revision_id": approved_id,
        }

    apply_runtime_slot_evidence(evidence)
    return {
        "slots_synced": len(evidence),
        "reference_evidence_ready": reference_evidence_ready(),
    }
