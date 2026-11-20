"""Provenance-only historical paper/key inventory (D12-13) — lawful years from registrations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import JEE_ADVANCED_PACK_CODE
from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    SourceSlotDescriptor,
    build_source_registry_snapshot,
)
from app.models import Source


class InventoryRightsStatus(StrEnum):
    RIGHTS_REVIEW_PENDING = "rights_review_pending"
    NOT_IN_REPO = "not_in_repo"


@dataclass(frozen=True, slots=True)
class HistoricalSlotRecord:
    slot_id: str
    academic_year: int | None
    document_role: str
    rights_status: InventoryRightsStatus
    staged_sha256: str | None
    approved_revision_id: str | None
    analyzable_items: bool


@dataclass(frozen=True, slots=True)
class HistoricalInventoryReport:
    slots: tuple[HistoricalSlotRecord, ...]
    issue_codes: tuple[str, ...]


def _registered_years(session: Session) -> set[int]:
    years: set[int] = set()
    sources = session.scalars(
        select(Source).where(Source.board_or_exam == JEE_ADVANCED_PACK_CODE)
    ).all()
    for source in sources:
        meta = source.metadata_json or {}
        year = meta.get("academic_year")
        if isinstance(year, int):
            years.add(year)
        elif isinstance(year, str) and year.isdigit():
            years.add(int(year))
    return years


def _year_for_slot(session: Session, slot: SourceSlotDescriptor) -> int | None:
    source = session.scalars(
        select(Source).where(Source.board_or_exam == "jee_advanced")
    ).all()
    for row in source:
        if row.metadata_json.get("slot_id") == slot.slot_id:
            year = row.metadata_json.get("academic_year")
            if isinstance(year, int):
                return year
            if isinstance(year, str) and year.isdigit():
                return int(year)
    registered = _registered_years(session)
    return 2026 if 2026 in registered else (min(registered) if registered else None)


def build_historical_inventory(session: Session) -> HistoricalInventoryReport:
    snapshot = build_source_registry_snapshot(session)
    slot_rows = snapshot.get("slots") or []
    records: list[HistoricalSlotRecord] = []
    issues: list[str] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        row = next((r for r in slot_rows if r["slot_id"] == slot.slot_id), None)
        sha = row.get("staged_sha256") if row else None
        approved = row.get("approved_revision_id") if row else None
        year = _year_for_slot(session, slot)
        if year is None:
            issues.append(f"{slot.slot_id}:academic_year_not_registered")
        if not sha:
            issues.append(f"{slot.slot_id}:original_bytes_not_in_repo")
        records.append(
            HistoricalSlotRecord(
                slot_id=slot.slot_id,
                academic_year=year,
                document_role=slot.document_role,
                rights_status=InventoryRightsStatus.RIGHTS_REVIEW_PENDING,
                staged_sha256=sha,
                approved_revision_id=approved,
                analyzable_items=False,
            )
        )
    if not any(r.analyzable_items for r in records):
        issues.append("item_level_evidence_not_analyzable")
    return HistoricalInventoryReport(
        slots=tuple(records),
        issue_codes=tuple(dict.fromkeys(issues)),
    )