from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.enums import SourceRevisionStatus
from app.models.source import SourceRevision

_OFFICIAL_AUTHORIZE_STATUSES = frozenset(
    {
        SourceRevisionStatus.ACTIVE.value,
        SourceRevisionStatus.APPROVED.value,
        SourceRevisionStatus.VALIDATED.value,
    }
)


def assess_source_revision_for_official_evidence(
    session: Session | None,
    revision_id: str | None,
) -> tuple[str, str | None]:
    """Return (outcome, detail) where outcome is ok | missing | fail | review."""
    if not revision_id:
        return "missing", "no_source_revision_id"
    if session is None:
        return "review", "session_unavailable"
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return "fail", "source_revision_not_found"
    status = revision.status
    if status in _OFFICIAL_AUTHORIZE_STATUSES:
        return "ok", status
    if status in {
        SourceRevisionStatus.STAGED.value,
        SourceRevisionStatus.EXTRACTED.value,
    }:
        return "fail", status
    if status in {
        SourceRevisionStatus.REJECTED.value,
        SourceRevisionStatus.FAILED.value,
        SourceRevisionStatus.SUPERSEDED.value,
    }:
        return "fail", status
    return "review", status
