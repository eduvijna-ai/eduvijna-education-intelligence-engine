from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.source import SourceRevision
from app.source_intelligence.approval_fingerprint import compute_revision_approval_fingerprint
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def verify_revision_storage_bytes_integrity(
    session: Session,
    revision: SourceRevision,
    *,
    storage_root: str | None = None,
) -> bool:
    """Verify stored source bytes still match revision.checksum (non-manual uploads)."""
    if not revision.storage_path or not revision.checksum:
        return False
    storage = (
        LocalSourceStorage(storage_root)
        if storage_root
        else SourceIntelligenceService(session).storage
    )
    service = SourceIntelligenceService(session, storage=storage)
    try:
        _, actual_checksum, integrity_ok = service._content_integrity(revision)
    except Exception:
        return False
    if not integrity_ok:
        return False
    return str(actual_checksum) == str(revision.checksum)


def verify_revision_approval_fingerprint_unchanged(
    session: Session, revision: SourceRevision
) -> bool:
    if not revision.approval_fingerprint:
        return False
    current = compute_revision_approval_fingerprint(session, revision)
    return current == str(revision.approval_fingerprint)
