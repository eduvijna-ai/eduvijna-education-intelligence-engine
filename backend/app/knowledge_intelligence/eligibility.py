from __future__ import annotations

from app.models.enums import SourceRevisionStatus
from app.models.source import SourceRevision


class IndexEligibilityError(ValueError):
    pass


_INDEXABLE_STATUSES = frozenset({SourceRevisionStatus.ACTIVE.value})


def assert_revision_index_eligible(revision: SourceRevision) -> None:
    if revision.status not in _INDEXABLE_STATUSES:
        raise IndexEligibilityError(
            f"Source revision {revision.id} is not index-eligible (status={revision.status})"
        )
    if not revision.extracted_text and not revision.metadata_json.get("synthetic_fixture"):
        raise IndexEligibilityError(
            f"Source revision {revision.id} has no extracted content for indexing"
        )
