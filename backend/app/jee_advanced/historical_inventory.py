"""Provenance-only historical paper/key inventory (D12-13) — no assumed item corpus."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    SourceSlotDescriptor,
    build_source_registry_snapshot,
)


class InventoryRightsStatus(StrEnum):
    RIGHTS_REVIEW_PENDING = "rights_review_pending"
    NOT_IN_REPO = "not_in_repo"


@dataclass(frozen=True, slots=True)
class HistoricalSlotRecord:
    slot_id: str
    academic_year: int
    document_role: str
    rights_status: InventoryRightsStatus
    staged_sha256: str | None
    approved_revision_id: str | None


@dataclass(frozen=True, slots=True)
class HistoricalInventoryReport:
    slots: tuple[HistoricalSlotRecord, ...]
    issue_codes: tuple[str, ...]


def _year_for_slot(slot: SourceSlotDescriptor) -> int:
    return 2026


def build_historical_inventory(session: Session) -> HistoricalInventoryReport:
    snapshot = build_source_registry_snapshot(session)
    slot_rows = snapshot.get("slots") or []
    records: list[HistoricalSlotRecord] = []
    issues: list[str] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        row = next((r for r in slot_rows if r["slot_id"] == slot.slot_id), None)
        sha = row.get("staged_sha256") if row else None
        approved = row.get("approved_revision_id") if row else None
        if not sha:
            issues.append(f"{slot.slot_id}:original_bytes_not_in_repo")
        records.append(
            HistoricalSlotRecord(
                slot_id=slot.slot_id,
                academic_year=_year_for_slot(slot),
                document_role=slot.document_role,
                rights_status=InventoryRightsStatus.RIGHTS_REVIEW_PENDING,
                staged_sha256=sha,
                approved_revision_id=approved,
            )
        )
    return HistoricalInventoryReport(
        slots=tuple(records),
        issue_codes=tuple(dict.fromkeys(issues)),
    )