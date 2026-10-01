from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.api.routes.system import readiness_check
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, request_context_middleware
from app.db.session import get_db
from app.schemas.system import HealthResponse

logger = logging.getLogger("eduvijna.errors")

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Eduvijna Education Intelligence Engine", version="0.1.0")
app.middleware("http")(request_context_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse, tags=["system"])
def ready(db: Session = Depends(get_db)) -> HealthResponse:
    return readiness_check(db)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
            }
        },
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return _error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled API exception",
        extra={"request_id": _request_id(request), "path": request.url.path},
    )
    return _error_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Internal server error",
    )
