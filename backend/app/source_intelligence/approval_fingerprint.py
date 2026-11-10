from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import SourceDiff, SourceRevision


def _sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_revision_approval_fingerprint(
    session: Session, revision: SourceRevision
) -> str:
    """Same digest as SourceIntelligenceService._approval_fingerprint (read-only reuse)."""
    source_diff = session.scalar(
        select(SourceDiff).where(SourceDiff.to_revision_id == revision.id)
    )
    payload = {
        "revision_id": revision.id,
        "checksum": revision.checksum,
        "source_snapshot_checksum": revision.source_snapshot_checksum,
        "extracted_checksum": revision.extracted_checksum,
        "validated_checksum": revision.validated_checksum,
        "extracted_text_checksum": _sha256(revision.extracted_text or ""),
        "content_type": revision.content_type,
        "byte_size": revision.byte_size,
        "diff_from_revision_id": (
            source_diff.from_revision_id if source_diff is not None else None
        ),
    }
    return _sha256(_canonical_json_bytes(payload))


def compute_source_snapshot_checksum(snapshot: dict[str, Any]) -> str:
    """Canonical checksum for approved source snapshot metadata (SourceIntelligenceService)."""
    from app.source_intelligence.service import SourceIntelligenceService

    return SourceIntelligenceService._snapshot_checksum(snapshot)


def verify_revision_stored_source_snapshot_checksum(revision: SourceRevision) -> bool:
    """Recompute checksum from stored snapshot metadata; detect tampered snapshot dict."""
    snapshot = (revision.metadata_json or {}).get("source_snapshot")
    if not isinstance(snapshot, dict):
        return False
    stored = str(revision.source_snapshot_checksum or "").strip()
    if not stored:
        return False
    return compute_source_snapshot_checksum(snapshot) == stored
