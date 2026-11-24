"""Day 17 REST catalogue under /api/v1."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.platform.auth.api_keys import create_api_key, revoke_api_key
from app.platform.auth.dependencies import get_request_correlation_id, require_principal
from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.auth.service import login, logout, refresh
from app.platform.capability_registry import (
    CapabilityDisposition,
    containment_snapshot,
    list_capabilities,
)
from app.platform.errors import CapabilityNotReadyError
from app.platform.jobs.service import cancel_job, get_job_for_principal
from app.platform.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from app.platform.schemas.common import CapabilityItem, CapabilityListResponse, JobResponse
from app.platform.schemas.endpoints import (
    AdminSourceUpsertRequest,
    AttemptSubmitRequest,
    GenerateMockExamRequest,
    GenerateQuestionsRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    RemediationRequest,
    ValidateQuestionRequest,
    ValidateQuestionResponse,
)
from app.platform.services.blocked import block_learner_capability, block_remediation_capability
from app.platform.services.curriculum import (
    get_curriculum,
    get_exam_pattern,
    list_curricula,
    list_exams,
)
from app.platform.services.knowledge import search_knowledge
from app.platform.services.questions import (
    submit_mock_exam_generation,
    submit_question_generation,
    validate_question,
)

router = APIRouter(tags=["platform"])


def _job_response(job) -> JobResponse:  # type: ignore[no-untyped-def]
    return JobResponse(
        id=UUID(job.id),
        status=job.status,
        capability_code=job.capability_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
        progress=job.progress_json,
        result=job.result_json,
        error_code=job.error_code,
        synthetic_fixture_only=job.synthetic_fixture_only,
    )


@router.post("/auth/login", response_model=TokenResponse)
def auth_login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_request_correlation_id),
) -> TokenResponse:
    tokens, _ = login(
        db,
        organization_code=body.organization_code,
        login_code=body.login_code,
        password=body.password,
        correlation_id=correlation_id,
    )
    db.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
def auth_refresh(
    body: RefreshRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_request_correlation_id),
) -> TokenResponse:
    tokens = refresh(db, refresh_token=body.refresh_token, correlation_id=correlation_id)
    db.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def auth_logout(
    body: LogoutRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_request_correlation_id),
) -> Response:
    logout(db, refresh_token=body.refresh_token, correlation_id=correlation_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=MeResponse)
def auth_me(principal: RequestPrincipal = Depends(require_principal)) -> MeResponse:
    return MeResponse(
        principal_id=UUID(principal.principal_id),
        organization_id=UUID(principal.organization_id),
        institution_id=UUID(principal.institution_id) if principal.institution_id else None,
        role=principal.role,
        scopes=list(principal.scopes),
        actor_kind=principal.actor_kind,
        actor_ref=principal.actor_ref,
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_key(
    body: ApiKeyCreateRequest,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> ApiKeyCreateResponse:
    require_permission(principal.scopes, "jobs:submit")
    issued = create_api_key(
        db,
        principal=principal,
        name=body.name,
        scopes=body.scopes,
        ttl_days=body.ttl_days,
    )
    db.commit()
    return ApiKeyCreateResponse(
        id=UUID(issued.record.id),
        name=issued.record.name,
        key_prefix=issued.record.key_prefix,
        secret=issued.secret,
        scopes=list(issued.record.scopes_json),
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(
    key_id: UUID,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> Response:
    revoke_api_key(db, principal=principal, key_id=str(key_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/capabilities", response_model=CapabilityListResponse)
def capabilities(
    principal: RequestPrincipal = Depends(require_principal),
) -> CapabilityListResponse:
    require_permission(principal.scopes, "capabilities:read")
    items = [
        CapabilityItem(
            code=record.code,
            disposition=record.disposition.value,
            reason=record.reason,
            scopes=sorted(record.scopes),
        )
        for record in list_capabilities()
    ]
    return CapabilityListResponse(capabilities=items, containment=containment_snapshot())


@router.get("/curricula")
def curricula(
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> dict[str, Any]:
    return {"items": list_curricula(db, principal=principal)}


@router.get("/curricula/{curriculum_id}")
def curriculum_detail(
    curriculum_id: UUID,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> Any:
    return get_curriculum(db, principal=principal, curriculum_id=curriculum_id)


@router.get("/exams")
def exams(
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> dict[str, Any]:
    return {"items": list_exams(db, principal=principal)}


@router.get("/exams/{exam_id}/versions")
def exam_versions(
    exam_id: UUID,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> dict[str, Any]:
    return get_exam_pattern(db, principal=principal, exam_id=exam_id)


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
def knowledge_search(
    body: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> KnowledgeSearchResponse:
    _ = db
    return search_knowledge(principal=principal, query=body.query, limit=body.limit)


@router.post(
    "/questions/generate",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def questions_generate(
    body: GenerateQuestionsRequest,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    try:
        submit_question_generation(
            db,
            principal=principal,
            topic_code=body.topic_code,
            count=body.count,
            idempotency_key=body.idempotency_key,
        )
    except CapabilityNotReadyError as exc:
        db.rollback()
        raise exc


@router.post("/questions/validate", response_model=ValidateQuestionResponse)
def questions_validate(
    body: ValidateQuestionRequest,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> ValidateQuestionResponse:
    return validate_question(db, principal=principal, question_text=body.question_text)


@router.post(
    "/tests/generate",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def tests_generate(
    body: GenerateMockExamRequest,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    try:
        submit_mock_exam_generation(
            db,
            principal=principal,
            exam_version_id=str(body.exam_version_id),
            question_count=body.question_count,
            idempotency_key=body.idempotency_key,
        )
    except CapabilityNotReadyError as exc:
        db.rollback()
        raise exc


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> JobResponse:
    require_permission(principal.scopes, "jobs:read")
    job = get_job_for_principal(db, principal=principal, job_id=str(job_id))
    return _job_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def job_cancel(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: RequestPrincipal = Depends(require_principal),
) -> JobResponse:
    require_permission(principal.scopes, "jobs:read")
    job = cancel_job(db, principal=principal, job_id=str(job_id))
    db.commit()
    return _job_response(job)


@router.post(
    "/attempts",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def attempts(
    body: AttemptSubmitRequest,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = body
    block_learner_capability("learners.attempt")


@router.get(
    "/learners/{learner_id}/mastery",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def learner_mastery(
    learner_id: UUID,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = learner_id
    block_learner_capability("learners.read")


@router.get(
    "/learners/{learner_id}/diagnostics",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def learner_diagnostics(
    learner_id: UUID,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = learner_id
    block_learner_capability("learners.read")


@router.get(
    "/learners/{learner_id}/misconceptions",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def learner_misconceptions(
    learner_id: UUID,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = learner_id
    block_learner_capability("learners.read")


@router.get(
    "/learners/{learner_id}/prerequisite-gaps",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def learner_gaps(
    learner_id: UUID,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = learner_id
    block_learner_capability("learners.read")


@router.post(
    "/learners/{learner_id}/remediation",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def learner_remediation(
    learner_id: UUID,
    body: RemediationRequest,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = learner_id
    _ = body
    block_remediation_capability("remediation.recommend")


@router.get("/admin/sources")
def admin_sources_list(
    principal: RequestPrincipal = Depends(require_principal),
) -> dict[str, Any]:
    require_permission(principal.scopes, "admin:sources")
    from app.platform.capability_registry import get_capability

    cap = get_capability("admin.sources")
    return {
        "items": [],
        "disposition": cap.disposition.value if cap else "blocked",
        "live_intake_disabled": True,
    }


@router.post(
    "/admin/sources",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    response_model=None,
)
def admin_sources_upsert(
    body: AdminSourceUpsertRequest,
    principal: RequestPrincipal = Depends(require_principal),
) -> None:
    _ = body
    require_permission(principal.scopes, "admin:sources")
    from app.platform.capability_registry import get_capability

    cap = get_capability("admin.sources")
    if cap and cap.disposition == CapabilityDisposition.SOURCE_PENDING:
        raise CapabilityNotReadyError(capability="admin.sources", reason=cap.reason)
    raise CapabilityNotReadyError(capability="admin.sources", reason="Source activation blocked")
