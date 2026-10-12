from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.enums import SourceRevisionStatus
from app.models.source import SourceRevision


def assess_source_revision_for_official_evidence(
    session: Session | None,
    revision_id: str | None,
) -> tuple[str, str | None]:
    """Return (outcome, detail) where outcome is ok | missing | fail | review.

    For new current official validation PASS, only ACTIVE SourceRevision may authorize.
    """
    if not revision_id:
        return "missing", "no_source_revision_id"
    if session is None:
        return "review", "session_unavailable"
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return "fail", "source_revision_not_found"
    status = revision.status
    if status == SourceRevisionStatus.ACTIVE.value:
        return "ok", status
    if status in {
        SourceRevisionStatus.VALIDATED.value,
        SourceRevisionStatus.APPROVED.value,
    }:
        return "fail", status
    if status in {
        SourceRevisionStatus.STAGED.value,
        SourceRevisionStatus.EXTRACTED.value,
        SourceRevisionStatus.REJECTED.value,
        SourceRevisionStatus.FAILED.value,
        SourceRevisionStatus.SUPERSEDED.value,
    }:
        return "fail", status
    return "review", status
