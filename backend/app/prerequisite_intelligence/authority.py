from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import CurriculumVersion
from app.models.enums import CurriculumStatus, SourceRevisionStatus, SourceStatus
from app.models.source import SourceRevision
from app.prerequisite_intelligence.contracts import GraphIssue, PrerequisiteGraphScope
from app.prerequisite_intelligence.enums import GraphIssueCode


@dataclass(slots=True)
class RevisionAuthorityRecord:
    revision_id: str
    status: str
    source_id: str
    source_status: str
    organization_id: str | None
    institution_id: str | None
    teacher_id: str | None
    bound_curriculum_version_ids: set[str]
    metadata_json: dict[str, Any]


@dataclass(slots=True)
class GraphAuthorityContext:
    curriculum_version_id: str
    curriculum_version_status: str
    authorized_revision_ids: set[str] = field(default_factory=set)
    revisions: dict[str, RevisionAuthorityRecord] = field(default_factory=dict)
    issues: list[GraphIssue] = field(default_factory=list)


def _revision_record(revision: SourceRevision) -> RevisionAuthorityRecord:
    source = revision.source
    bound = {version.id for version in revision.curriculum_versions}
    return RevisionAuthorityRecord(
        revision_id=revision.id,
        status=revision.status,
        source_id=revision.source_id,
        source_status=source.status if source is not None else "",
        organization_id=source.organization_id if source is not None else None,
        institution_id=source.institution_id if source is not None else None,
        teacher_id=source.teacher_id if source is not None else None,
        bound_curriculum_version_ids=bound,
        metadata_json=dict(revision.metadata_json or {}),
    )


def build_graph_authority_context(
    session: Session, scope: PrerequisiteGraphScope
) -> GraphAuthorityContext:
    issues: list[GraphIssue] = []
    version = session.get(CurriculumVersion, scope.curriculum_version_id)
    if version is None:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.CROSS_VERSION_EDGE,
                severity="error",
                field_path="scope.curriculum_version_id",
            )
        )
        return GraphAuthorityContext(
            curriculum_version_id=scope.curriculum_version_id,
            curriculum_version_status="missing",
            issues=issues,
        )

    if version.status != CurriculumStatus.ACTIVE.value:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.STALE_CURRICULUM_VERSION,
                severity="error",
                field_path="scope.curriculum_version_id",
                detail={"status": version.status},
            )
        )

    revision_ids: set[str] = set()
    if version.source_revision_id:
        revision_ids.add(version.source_revision_id)
    for source in version.sources:
        for revision in source.revisions:
            revision_ids.add(revision.id)

    loaded = (
        session.scalars(
            select(SourceRevision).where(SourceRevision.id.in_(revision_ids or {"__none__"}))
        ).all()
        if revision_ids
        else []
    )
    records: dict[str, RevisionAuthorityRecord] = {}
    authorized: set[str] = set()
    for revision in loaded:
        record = _revision_record(revision)
        records[revision.id] = record
        if revision_is_authorized_for_scope(record, scope, scope.curriculum_version_id):
            authorized.add(revision.id)

    return GraphAuthorityContext(
        curriculum_version_id=scope.curriculum_version_id,
        curriculum_version_status=version.status,
        authorized_revision_ids=authorized,
        revisions=records,
        issues=issues,
    )


def revision_is_authorized_for_scope(
    record: RevisionAuthorityRecord,
    scope: PrerequisiteGraphScope,
    curriculum_version_id: str,
) -> bool:
    if record.status != SourceRevisionStatus.ACTIVE.value:
        return False
    if curriculum_version_id not in record.bound_curriculum_version_ids:
        return False
    if record.source_status != SourceStatus.ACTIVE.value:
        return False
    if scope.organization_id and record.organization_id != scope.organization_id:
        return False
    if scope.institution_id and record.institution_id != scope.institution_id:
        return False
    if scope.teacher_id and record.teacher_id != scope.teacher_id:
        return False
    if record.metadata_json.get("synthetic") or record.metadata_json.get("synthetic_fixture"):
        return False
    return True


def load_revision_record(session: Session, revision_id: str) -> RevisionAuthorityRecord | None:
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return None
    return _revision_record(revision)
