from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.models.curriculum import CurriculumVersion
from app.models.enums import CurriculumStatus
from app.prerequisite_intelligence.contracts import (
    PrerequisiteGraphScope,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.loader import load_prerequisite_graph_snapshot
from app.root_cause_intelligence.enums import RootCauseIssueCode

_SCOPE_FIELDS = (
    "organization_id",
    "institution_id",
    "teacher_id",
    "medium_code",
    "subject_code",
    "grade_year_code",
)
_TENANT_FIELDS = ("organization_id", "institution_id", "teacher_id")


def _scope_field(scope: PrerequisiteGraphScope, field: str) -> str | None:
    return getattr(scope, field, None)


def _strict_scope_mismatch(
    requested: str | None,
    authoritative: str | None,
) -> bool:
    if requested and not authoritative:
        return True
    if requested and authoritative and requested != authoritative:
        return True
    return False


def verify_production_graph_snapshot(
    session: Session | None,
    snapshot: PrerequisiteGraphSnapshot,
    *,
    organization_id: str | None,
    institution_id: str | None,
    teacher_id: str | None,
    execution_mode: TrustExecutionMode,
) -> tuple[list[RootCauseIssueCode], list[str], bool]:
    issues: list[RootCauseIssueCode] = []
    paths: list[str] = []
    meta = snapshot.metadata_json or {}

    recomputed = PrerequisiteGraphSnapshot.compute_checksum(
        snapshot.scope,
        snapshot.nodes,
        snapshot.edges,
        snapshot.graph_version,
    )
    if recomputed != snapshot.checksum:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.checksum")
        return issues, paths, True

    request_scope = {
        "organization_id": organization_id,
        "institution_id": institution_id,
        "teacher_id": teacher_id,
    }

    if execution_mode == TrustExecutionMode.SYNTHETIC_FIXTURE:
        if not meta.get("loader_attested") and not meta.get("synthetic_fixture"):
            issues.append(RootCauseIssueCode.MISSING_GRAPH)
            paths.append("graph_snapshot.loader_attested")
        loader_scope = meta.get("loader_scope") or {}
        for field in _TENANT_FIELDS:
            if _strict_scope_mismatch(request_scope.get(field), loader_scope.get(field)):
                issues.append(RootCauseIssueCode.FOREIGN_TENANT)
                paths.append(f"graph_snapshot.scope.{field}")
        return issues, paths, bool(issues)

    if session is None:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.session")
        return issues, paths, True

    version = session.get(CurriculumVersion, snapshot.scope.curriculum_version_id)
    if version is None or version.status != CurriculumStatus.ACTIVE.value:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.curriculum_version")
        return issues, paths, True

    if (
        meta.get("synthetic_fixture")
        or meta.get("fixture")
        or (version.metadata_json or {}).get("fixture")
    ):
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.fixture_forbidden_in_production")
        return issues, paths, True

    if not meta.get("loader_attested"):
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.loader_attested")
        return issues, paths, True

    canonical = load_prerequisite_graph_snapshot(session, snapshot.scope)
    if canonical.checksum != snapshot.checksum or canonical.snapshot_id != snapshot.snapshot_id:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.canonical_mismatch")
        return issues, paths, True

    canonical_meta = canonical.metadata_json or {}
    canonical_loader = canonical_meta.get("loader_scope") or {}
    claimed_loader = meta.get("loader_scope") or {}

    for field in _SCOPE_FIELDS:
        snap_val = _scope_field(snapshot.scope, field)
        canon_val = _scope_field(canonical.scope, field)
        if snap_val != canon_val:
            issues.append(RootCauseIssueCode.MISSING_GRAPH)
            paths.append(f"graph_snapshot.scope.{field}")
            continue

        req_val = request_scope.get(field) if field in _TENANT_FIELDS else None
        if field in _TENANT_FIELDS:
            req_val = request_scope.get(field)
        elif field == "medium_code":
            req_val = snapshot.scope.medium_code
        elif field == "subject_code":
            req_val = snapshot.scope.subject_code
        elif field == "grade_year_code":
            req_val = snapshot.scope.grade_year_code

        if field in _TENANT_FIELDS:
            if _strict_scope_mismatch(req_val, snap_val):
                issues.append(RootCauseIssueCode.FOREIGN_TENANT)
                paths.append(f"graph_snapshot.scope.{field}")
            if snap_val and not req_val:
                issues.append(RootCauseIssueCode.FOREIGN_TENANT)
                paths.append(f"graph_snapshot.scope.{field}")

        canon_loader_val = canonical_loader.get(field)
        claimed_loader_val = claimed_loader.get(field)
        if claimed_loader_val != canon_loader_val:
            issues.append(RootCauseIssueCode.FOREIGN_TENANT)
            paths.append(f"graph_snapshot.loader_scope.{field}")
        if snap_val and canon_loader_val and snap_val != canon_loader_val:
            issues.append(RootCauseIssueCode.MISSING_GRAPH)
            paths.append(f"graph_snapshot.loader_scope.{field}")

    blocking = bool(issues)
    return issues, paths, blocking
