from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.enums import SourceExtractionStatus, SourceRevisionStatus
from app.models.source import SourceRevision
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def _canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ensure_genuine_source_content_approval(
    session: Session,
    tmp_path: Path,
    revision_id: str,
    *,
    actor_id: str = "founder-day10-trust",
    source_locator: str,
) -> SourceRevision:
    """Run the real source validate → approve → activate lifecycle for a manual revision."""
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        raise AssertionError("revision missing")
    source = revision.source
    if not source.authority:
        source.authority = "Synthetic Education Authority"
        session.flush()
    manual_metadata = {
        "document_type": "official_misconception_mapping_table",
        "locator": source_locator,
        "excerpt": (
            "Whole-number addition off-by-one-low maps to whole-number and multi-step addition."
        ),
    }
    content = _canonical_json_bytes(manual_metadata)
    from app.source_intelligence.service import _sha256

    checksum = _sha256(content)
    storage = LocalSourceStorage(tmp_path / "day10-source-store")
    service = SourceIntelligenceService(session, storage=storage)
    snapshot = service._source_snapshot(source)
    snapshot_checksum = service._snapshot_checksum(snapshot)
    revision.metadata_json = {
        **(revision.metadata_json or {}),
        "manual_metadata": manual_metadata,
        "source_snapshot": snapshot,
    }
    revision.checksum = checksum
    revision.extracted_checksum = checksum
    revision.validated_checksum = None
    revision.byte_size = len(content)
    revision.content_type = "application/json"
    revision.extraction_status = SourceExtractionStatus.SUCCEEDED.value
    revision.extracted_text = json.dumps(manual_metadata, sort_keys=True)
    revision.source_snapshot_checksum = snapshot_checksum
    revision.status = SourceRevisionStatus.EXTRACTED.value
    revision.active_slot = None
    revision.approval_fingerprint = None
    revision.approved_by = None
    revision.approved_at = None
    session.flush()
    service.create_diff(revision.id, actor_id=actor_id)
    validation = service.validate_revision(revision.id, actor_id=actor_id)
    if not validation.valid:
        raise AssertionError(f"source validation failed: {validation.errors}")
    service.approve_revision(revision.id, actor_id=actor_id)
    service.activate_revision(revision.id, actor_id=actor_id)
    session.refresh(revision)
    return revision
