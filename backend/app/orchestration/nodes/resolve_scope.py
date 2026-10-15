from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.curriculum import CurriculumVersion
from app.models.examination import ExamVersion
from app.orchestration.contracts import ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.state import OrchestrationGraphState


def _validate_refs(session: Session, request_scope: ResolvedScope) -> ResolvedScope:
    warnings: list[str] = []
    errors: list[str] = []
    if request_scope.curriculum_version_id:
        version = session.get(CurriculumVersion, request_scope.curriculum_version_id)
        if version is None:
            errors.append("curriculum_version_not_found")
        elif version.status != "active":
            errors.append("curriculum_version_inactive")
    if request_scope.exam_version_id:
        exam = session.get(ExamVersion, request_scope.exam_version_id)
        if exam is None:
            errors.append("exam_version_not_found")
    return request_scope.model_copy(
        update={"scope_warnings": warnings, "scope_errors": errors}
    )


def resolve_scope_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    scope = ResolvedScope(
        curriculum_version_id=request.curriculum_version_id,
        exam_version_id=request.exam_version_id,
        grade_year_code=request.grade_year_code,
        medium_code=request.medium_code,
        subject_code=request.subject_code,
        organization_id=request.organization_id,
        institution_id=request.institution_id,
        actor_id=request.actor_id,
    )
    scope = _validate_refs(deps.session, scope)
    status = (
        OrchestrationRunStatus.FAILED.value
        if scope.scope_errors
        else OrchestrationRunStatus.PLANNING.value
    )
    audit_node(deps, state, "resolve_scope", status, payload={"errors": scope.scope_errors})
    update = {
        "resolved_scope": scope.model_dump(mode="json"),
        "status": status,
        "errors": scope.scope_errors,
    }
    return timed_update(state, "resolve_scope", started, update)
