from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.constants import COPYRIGHT_RIGHTS_RESERVED_REVIEW, JEE_ADVANCED_AUTHORITY
from app.jee_advanced.source_authority import evaluate_reference_authority
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS, _find_slot_source
from app.models.enums import SourceTrustTier, SourceType
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService


def register_discovery_sources(session: Session) -> list[str]:
    """D12-02/03: Stage official discovery metadata via Day3; never fabricate approval."""

    service = SourceIntelligenceService(session)
    registered: list[str] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        existing = _find_slot_source(session, slot.slot_id)
        if existing is not None:
            registered.append(str(existing.id))
            continue
        if slot.source_type_label == "official_paper":
            source_type = SourceType.OFFICIAL_PAPER
        elif slot.source_type_label == "answer_key":
            source_type = SourceType.ANSWER_KEY
        elif slot.source_type_label == "official_syllabus":
            source_type = SourceType.OFFICIAL_SYLLABUS
        else:
            source_type = SourceType.OFFICIAL_EXAM_BULLETIN
        payload = SourceRegistrationInput(
            source_type=source_type,
            title=slot.title,
            url=slot.discovery_url,
            authority=JEE_ADVANCED_AUTHORITY,
            country="IN",
            board_or_exam="jee_advanced",
            academic_year="2026",
            copyright_classification=COPYRIGHT_RIGHTS_RESERVED_REVIEW,
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json={
                "slot_id": slot.slot_id,
                "jee_advanced_slot": True,
                "ingest_status": "DISCOVERED",
                "lifecycle_status": "DISCOVERED",
                "copyright_classification": COPYRIGHT_RIGHTS_RESERVED_REVIEW,
                "rights_review_status": slot.rights_review_status,
                "direct_pdf_url": slot.discovery_url,
                "human_rights_disposition": None,
                "document_role": slot.document_role,
                "paper_code": slot.paper_code,
                "language": slot.language,
            },
        )
        source = service.register_source(payload)
        session.flush()
        registered.append(str(source.id))
    session.commit()
    return registered


def sync_slot_evidence_from_session(session: Session) -> dict[str, Any]:
    """Read-only authority evaluation; does not cache approval in module globals."""

    authority = evaluate_reference_authority(session)
    evidence: dict[str, dict[str, str | None]] = {}
    for slot_result in authority.slots:
        evidence[slot_result.slot_id] = {
            "source_id": slot_result.source_id,
            "staged_sha256": None,
            "approved_revision_id": (
                slot_result.revision_id if slot_result.trusted else None
            ),
            "trusted": "true" if slot_result.trusted else "false",
        }
    return {
        "slots_synced": len(evidence),
        "reference_evidence_ready": authority.ready,
        "authority_issues": list(authority.issues),
    }
