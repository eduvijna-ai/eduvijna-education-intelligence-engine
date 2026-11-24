from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationApiKey
from app.platform.auth.passwords import hash_password, verify_password
from app.platform.auth.principal import RequestPrincipal, assert_tenant_active
from app.platform.errors import AuthenticationError, AuthorizationError, NotFoundError


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    record: ApplicationApiKey
    secret: str


def _split_api_key(raw: str) -> tuple[str, str]:
    if "." not in raw:
        raise AuthenticationError("Invalid API key format")
    prefix, secret = raw.split(".", 1)
    if not prefix or not secret:
        raise AuthenticationError("Invalid API key format")
    return prefix, secret


def create_api_key(
    session: Session,
    *,
    principal: RequestPrincipal,
    name: str,
    scopes: list[str],
    ttl_days: int | None = 90,
) -> IssuedApiKey:
    assert_tenant_active(session, principal.organization_id, principal.institution_id)
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    record = ApplicationApiKey(
        id=uuid.uuid4().hex,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        created_by_principal_id=principal.principal_id,
        key_prefix=prefix,
        secret_hash_json=hash_password(secret),
        name=name,
        scopes_json=scopes,
        expires_at=(datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days is not None else None),
        active=True,
    )
    session.add(record)
    session.flush()
    return IssuedApiKey(record=record, secret=f"{prefix}.{secret}")


def revoke_api_key(session: Session, *, principal: RequestPrincipal, key_id: str) -> None:
    record = session.scalar(
        select(ApplicationApiKey).where(
            ApplicationApiKey.id == key_id,
            ApplicationApiKey.organization_id == principal.organization_id,
        )
    )
    if record is None:
        raise NotFoundError("API key not found")
    if record.institution_id and record.institution_id != principal.institution_id:
        raise AuthorizationError("Cross-tenant API key access denied")
    record.active = False
    record.revoked_at = datetime.now(UTC)


def authenticate_api_key(session: Session, raw_key: str) -> RequestPrincipal:
    prefix, secret = _split_api_key(raw_key)
    record = session.scalar(select(ApplicationApiKey).where(ApplicationApiKey.key_prefix == prefix))
    if record is None or not record.active:
        raise AuthenticationError("Invalid API key")
    if record.revoked_at is not None:
        raise AuthenticationError("API key revoked")
    if record.expires_at:
        key_expires = record.expires_at
        if key_expires.tzinfo is None:
            key_expires = key_expires.replace(tzinfo=UTC)
        if key_expires < datetime.now(UTC):
            raise AuthenticationError("API key expired")
    if not verify_password(secret, record.secret_hash_json):
        raise AuthenticationError("Invalid API key")
    assert_tenant_active(session, record.organization_id, record.institution_id)
    scopes = tuple(str(s) for s in record.scopes_json)
    return RequestPrincipal(
        principal_id=record.created_by_principal_id or record.id,
        organization_id=record.organization_id,
        institution_id=record.institution_id,
        role="api_key",
        scopes=scopes,
        actor_kind="api_key",
        actor_ref=record.id,
        auth_method="api_key",
    )
