from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.platform.schemas.common import StrictModel


class LoginRequest(StrictModel):
    organization_code: str = Field(min_length=1, max_length=128)
    login_code: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(StrictModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(StrictModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class LogoutRequest(StrictModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class MeResponse(StrictModel):
    principal_id: UUID
    organization_id: UUID
    institution_id: UUID | None
    role: str
    scopes: list[str]
    actor_kind: str
    actor_ref: str


class ApiKeyCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(min_length=1, max_length=32)
    ttl_days: int | None = Field(default=90, ge=1, le=365)


class ApiKeyCreateResponse(StrictModel):
    id: UUID
    name: str
    key_prefix: str
    secret: str
    scopes: list[str]
    display_once: bool = True
