from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    OFFICIAL_DISCOVERY_URLS,
    SOURCE_SLOT_BROCHURE,
    SOURCE_SLOT_KEY_PAPER1,
    SOURCE_SLOT_KEY_PAPER2,
    SOURCE_SLOT_PAPER1,
    SOURCE_SLOT_PAPER2,
    SOURCE_SLOT_SYLLABUS,
)
from app.jee_advanced.enums import JeeAdvancedSourceTrustMode
from app.models import Source, SourceRevision
from app.models.enums import SourceRevisionStatus


def _find_slot_source(session: Session, slot_id: str) -> Source | None:
    candidates = session.scalars(
        select(Source).where(Source.board_or_exam == "jee_advanced")
    ).all()
    for source in candidates:
        if source.metadata_json.get("slot_id") == slot_id:
            return source
    return None


@dataclass(frozen=True, slots=True)
class SourceSlotDescriptor:
    slot_id: str
    title: str
    discovery_url: str | None
    trust_mode: JeeAdvancedSourceTrustMode
    requires_curator_approval: bool
    staged_sha256: str | None
    approved_revision_id: str | None
    source_id: str | None = None
    document_role: str = ""
    source_type_label: str = ""
    paper_code: str | None = None
    language: str = "en"
    rights_review_status: str = "RIGHTS_REVIEW_PENDING"


def _slot(
    slot_id: str,
    title: str,
    url_key: str,
    *,
    document_role: str,
    source_type_label: str,
    paper_code: str | None = None,
    language: str = "en",
) -> SourceSlotDescriptor:
    return SourceSlotDescriptor(
        slot_id=slot_id,
        title=title,
        discovery_url=OFFICIAL_DISCOVERY_URLS.get(url_key, None),
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        requires_curator_approval=True,
        staged_sha256=None,
        approved_revision_id=None,
        document_role=document_role,
        source_type_label=source_type_label,
        paper_code=paper_code,
        language=language,
        rights_review_status="RIGHTS_REVIEW_PENDING",
    )


JEE_ADVANCED_2026_SOURCE_SLOTS: tuple[SourceSlotDescriptor, ...] = (
    _slot(
        SOURCE_SLOT_BROCHURE,
        "JEE Advanced 2026 Information Brochure (English)",
        "brochure_en_2026",
        document_role="information_brochure",
        source_type_label="official_exam_bulletin",
    ),
    _slot(
        SOURCE_SLOT_SYLLABUS,
        "JEE Advanced 2026 Official Syllabus",
        "syllabus_2026",
        document_role="official_syllabus",
        source_type_label="official_syllabus",
    ),
    _slot(
        SOURCE_SLOT_PAPER1,
        "JEE Advanced 2026 official Paper 1",
        "paper1_en_2026",
        document_role="question_paper",
        source_type_label="official_paper",
        paper_code="paper_1",
    ),
    _slot(
        SOURCE_SLOT_PAPER2,
        "JEE Advanced 2026 official Paper 2",
        "paper2_en_2026",
        document_role="question_paper",
        source_type_label="official_paper",
        paper_code="paper_2",
    ),
    _slot(
        SOURCE_SLOT_KEY_PAPER1,
        "JEE Advanced 2026 final answer key Paper 1",
        "key_paper1_final_2026",
        document_role="final_answer_key",
        source_type_label="answer_key",
        paper_code="paper_1",
    ),
    _slot(
        SOURCE_SLOT_KEY_PAPER2,
        "JEE Advanced 2026 final answer key Paper 2",
        "key_paper2_final_2026",
        document_role="final_answer_key",
        source_type_label="answer_key",
        paper_code="paper_2",
    ),
)


def reference_evidence_ready(session: Session | None = None) -> bool:
    """True only when every required slot passes persisted authority checks."""

    from app.jee_advanced.source_authority import reference_evidence_ready as _ready

    return _ready(session)


def build_source_registry_snapshot(session: Session | None = None) -> dict[str, Any]:
    """D12-02/03 staging metadata without claiming ingest or curator approval."""

    from app.jee_advanced.source_authority import evaluate_reference_authority

    authority = evaluate_reference_authority(session)
    slots: list[dict[str, Any]] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        slot_auth = next((s for s in authority.slots if s.slot_id == slot.slot_id), None)
        approved = slot_auth.revision_id if slot_auth and slot_auth.trusted else None
        staged_sha: str | None = None
        source_id = slot_auth.source_id if slot_auth else None
        if session is not None and slot_auth and slot_auth.revision_id:
            revision = session.get(SourceRevision, slot_auth.revision_id)
            if revision is not None:
                staged_sha = revision.checksum
        elif session is not None:
            source = _find_slot_source(session, slot.slot_id)
            if source is not None:
                source_id = str(source.id)
                revision = session.scalar(
                    select(SourceRevision)
                    .where(
                        SourceRevision.source_id == source.id,
                        SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
                    )
                    .order_by(SourceRevision.revision_number.desc())
                )
                if revision is not None:
                    staged_sha = revision.checksum
                    approved = None
        slots.append(
            {
                "slot_id": slot.slot_id,
                "title": slot.title,
                "discovery_url": slot.discovery_url,
                "staged_sha256": staged_sha,
                "approved_revision_id": approved,
                "source_id": source_id,
                "status": "APPROVED" if approved else "SOURCE_PENDING",
                "authority_issues": list(slot_auth.issues) if slot_auth else [],
            }
        )

    return {
        "trust_boundary": "curator_approved_bytes_required_for_reference_replica",
        "slot_count": len(slots),
        "slots": slots,
        "reference_evidence_ready": authority.ready,
        "authority_issues": list(authority.issues),
    }
