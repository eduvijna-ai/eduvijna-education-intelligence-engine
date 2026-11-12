from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.jee_advanced.constants import (
    OFFICIAL_DISCOVERY_URLS,
    SOURCE_SLOT_BROCHURE,
    SOURCE_SLOT_SYLLABUS,
)
from app.jee_advanced.enums import JeeAdvancedSourceTrustMode


@dataclass(frozen=True, slots=True)
class SourceSlotDescriptor:
    slot_id: str
    title: str
    discovery_url: str | None
    trust_mode: JeeAdvancedSourceTrustMode
    requires_curator_approval: bool
    staged_sha256: str | None
    approved_revision_id: str | None


JEE_ADVANCED_2026_SOURCE_SLOTS: tuple[SourceSlotDescriptor, ...] = (
    SourceSlotDescriptor(
        slot_id=SOURCE_SLOT_BROCHURE,
        title="JEE Advanced 2026 Information Brochure (English)",
        discovery_url=OFFICIAL_DISCOVERY_URLS["brochure_en_2026"],
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        requires_curator_approval=True,
        staged_sha256=None,
        approved_revision_id=None,
    ),
    SourceSlotDescriptor(
        slot_id=SOURCE_SLOT_SYLLABUS,
        title="JEE Advanced 2026 Official Syllabus",
        discovery_url=OFFICIAL_DISCOVERY_URLS["syllabus_2026"],
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        requires_curator_approval=True,
        staged_sha256=None,
        approved_revision_id=None,
    ),
)


def reference_evidence_ready() -> bool:
    """True only when every required slot has an approved revision (no fabricated approval)."""

    return all(slot.approved_revision_id for slot in JEE_ADVANCED_2026_SOURCE_SLOTS)


def build_source_registry_snapshot() -> dict[str, Any]:
    """D12-02 staging metadata without claiming ingest or curator approval."""

    return {
        "trust_boundary": "curator_approved_bytes_required_for_reference_replica",
        "slots": [
            {
                "slot_id": slot.slot_id,
                "title": slot.title,
                "discovery_url": slot.discovery_url,
                "staged_sha256": slot.staged_sha256,
                "approved_revision_id": slot.approved_revision_id,
                "status": "SOURCE_PENDING" if not slot.approved_revision_id else "APPROVED",
            }
            for slot in JEE_ADVANCED_2026_SOURCE_SLOTS
        ],
        "reference_evidence_ready": reference_evidence_ready(),
    }
