from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def _slot(
    slot_id: str,
    title: str,
    url_key: str | None,
) -> SourceSlotDescriptor:
    return SourceSlotDescriptor(
        slot_id=slot_id,
        title=title,
        discovery_url=OFFICIAL_DISCOVERY_URLS.get(url_key or "", None),
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        requires_curator_approval=True,
        staged_sha256=None,
        approved_revision_id=None,
    )


JEE_ADVANCED_2026_SOURCE_SLOTS: tuple[SourceSlotDescriptor, ...] = (
    _slot(
        SOURCE_SLOT_BROCHURE,
        "JEE Advanced 2026 Information Brochure (English)",
        "brochure_en_2026",
    ),
    _slot(SOURCE_SLOT_SYLLABUS, "JEE Advanced 2026 Official Syllabus", "syllabus_2026"),
    _slot(SOURCE_SLOT_PAPER1, "JEE Advanced 2026 official Paper 1", "site_home"),
    _slot(SOURCE_SLOT_PAPER2, "JEE Advanced 2026 official Paper 2", "site_home"),
    _slot(SOURCE_SLOT_KEY_PAPER1, "JEE Advanced 2026 final answer key Paper 1", "site_home"),
    _slot(SOURCE_SLOT_KEY_PAPER2, "JEE Advanced 2026 final answer key Paper 2", "site_home"),
)

# Runtime overlay populated by Day3 lifecycle sync (never forge approval).
_SLOT_RUNTIME: dict[str, dict[str, str | None]] = {}


def apply_runtime_slot_evidence(evidence: dict[str, dict[str, str | None]]) -> None:
    _SLOT_RUNTIME.clear()
    _SLOT_RUNTIME.update(evidence)


def reference_evidence_ready() -> bool:
    """True only when every required slot has an approved revision (no fabricated approval)."""

    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        runtime = _SLOT_RUNTIME.get(slot.slot_id, {})
        approved = runtime.get("approved_revision_id") or slot.approved_revision_id
        if not approved:
            return False
    return True


def build_source_registry_snapshot() -> dict[str, Any]:
    """D12-02/03 staging metadata without claiming ingest or curator approval."""

    slots: list[dict[str, Any]] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        runtime = _SLOT_RUNTIME.get(slot.slot_id, {})
        staged_sha = runtime.get("staged_sha256") or slot.staged_sha256
        approved = runtime.get("approved_revision_id") or slot.approved_revision_id
        slots.append(
            {
                "slot_id": slot.slot_id,
                "title": slot.title,
                "discovery_url": slot.discovery_url,
                "staged_sha256": staged_sha,
                "approved_revision_id": approved,
                "source_id": runtime.get("source_id") or slot.source_id,
                "status": "SOURCE_PENDING" if not approved else "APPROVED",
            }
        )

    return {
        "trust_boundary": "curator_approved_bytes_required_for_reference_replica",
        "slot_count": len(slots),
        "slots": slots,
        "reference_evidence_ready": reference_evidence_ready(),
    }
