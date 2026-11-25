from fastapi import APIRouter

from app.api.routes.platform import router as platform_router
from app.api.routes.system import router as system_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system_router)
api_router.include_router(platform_router)
