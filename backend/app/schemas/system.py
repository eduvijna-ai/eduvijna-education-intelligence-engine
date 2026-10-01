from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class SystemInfoResponse(BaseModel):
    service: str
    status: str
    environment: str
    api_version: str


class DomainModelInfoResponse(BaseModel):
    version: str
    curriculum_node_types: list[str]
    question_types: list[str]
    source_types: list[str]
    diagnostic_categories: list[str]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
