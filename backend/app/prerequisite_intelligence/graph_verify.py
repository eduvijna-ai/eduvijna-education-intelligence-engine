from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.models.curriculum import CurriculumVersion
from app.models.enums import CurriculumStatus
from app.prerequisite_intelligence.contracts import PrerequisiteGraphSnapshot
from app.prerequisite_intelligence.loader import load_prerequisite_graph_snapshot
from app.root_cause_intelligence.enums import RootCauseIssueCode


def _strict_scope_mismatch(
    field: str,
    requested: str | None,
    attested: str | None,
) -> bool:
    if requested and not attested:
        return True
    if requested and attested and requested != attested:
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

    if execution_mode == TrustExecutionMode.SYNTHETIC_FIXTURE:
        if not meta.get("loader_attested") and not meta.get("synthetic_fixture"):
            issues.append(RootCauseIssueCode.MISSING_GRAPH)
            paths.append("graph_snapshot.loader_attested")
        loader_scope = meta.get("loader_scope") or {}
        scope = snapshot.scope
        if _strict_scope_mismatch(
            "institution_id", institution_id, loader_scope.get("institution_id")
        ):
            issues.append(RootCauseIssueCode.FOREIGN_TENANT)
            paths.append("graph_snapshot.scope.institution_id")
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

    loader_scope = meta.get("loader_scope") or {}
    scope = snapshot.scope
    for field, req_val, loader_val in (
        ("organization_id", organization_id, loader_scope.get("organization_id")),
        ("institution_id", institution_id, loader_scope.get("institution_id")),
        ("teacher_id", teacher_id, loader_scope.get("teacher_id")),
        ("medium_code", scope.medium_code, loader_scope.get("medium_code")),
        ("subject_code", scope.subject_code, loader_scope.get("subject_code")),
        ("grade_year_code", scope.grade_year_code, loader_scope.get("grade_year_code")),
    ):
        if _strict_scope_mismatch(field, req_val, loader_val):
            issues.append(RootCauseIssueCode.FOREIGN_TENANT)
            paths.append(f"graph_snapshot.scope.{field}")

    canonical = load_prerequisite_graph_snapshot(session, snapshot.scope)
    if canonical.checksum != snapshot.checksum or canonical.snapshot_id != snapshot.snapshot_id:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.canonical_mismatch")

    blocking = bool(issues)
    return issues, paths, blocking
