from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import (
    CurriculumNodeType,
    DiagnosticCategory,
    QuestionType,
    SourceType,
)
from app.schemas.system import (
    DomainModelInfoResponse,
    HealthResponse,
    SystemInfoResponse,
)

router = APIRouter(tags=["system"])


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(settings: Settings = Depends(get_settings)) -> SystemInfoResponse:
    return SystemInfoResponse(
        service="eduvijna-api",
        status="ok",
        environment=settings.app_env,
        api_version="v1",
    )


@router.get("/system/domain-model", response_model=DomainModelInfoResponse)
def domain_model_info() -> DomainModelInfoResponse:
    return DomainModelInfoResponse(
        version="d02",
        curriculum_node_types=[item.value for item in CurriculumNodeType],
        question_types=[item.value for item in QuestionType],
        source_types=[item.value for item in SourceType],
        diagnostic_categories=[item.value for item in DiagnosticCategory],
    )


def readiness_check(db: Session) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ready")
