from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class SystemInfoResponse(BaseModel):
    service: str
    status: str
    environment: str
    api_version: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
