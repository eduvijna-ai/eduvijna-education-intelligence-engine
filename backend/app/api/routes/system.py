from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.system import HealthResponse, SystemInfoResponse

router = APIRouter(tags=["system"])


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(settings: Settings = Depends(get_settings)) -> SystemInfoResponse:
    return SystemInfoResponse(
        service="eduvijna-api",
        status="ok",
        environment=settings.app_env,
        api_version="v1",
    )


def readiness_check(db: Session) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ready")
