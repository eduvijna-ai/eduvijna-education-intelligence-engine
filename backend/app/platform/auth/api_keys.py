from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationApiKey
from app.platform.auth.audit import record_security_event
from app.platform.auth.delegation import assert_scopes_subset, delegatable_scopes_for_role
from app.platform.auth.passwords import hash_password, verify_password
from app.platform.auth.principal import (
    RequestPrincipal,
    assert_tenant_active,
    load_and_validate_principal,
    request_principal_from_api_key,
)
from app.platform.auth.rbac import require_permission
from app.platform.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.platform.ids import canonical_id


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
    correlation_id: str = "unknown",
) -> IssuedApiKey:
    require_permission(principal.scopes, "api_keys:manage")
    if principal.auth_method == "api_key":
        raise AuthorizationError("API keys cannot mint API keys")
    allowed = delegatable_scopes_for_role(principal.role)
    granted = assert_scopes_subset(scopes, allowed)
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
        scopes_json=list(granted),
        expires_at=(datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days is not None else None),
        active=True,
    )
    session.add(record)
    session.flush()
    record_security_event(
        session,
        event_type="auth.api_key.create",
        correlation_id=correlation_id,
        success=True,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        principal_id=principal.principal_id,
        metadata={"key_prefix": prefix, "scopes": list(granted)},
    )
    return IssuedApiKey(record=record, secret=f"{prefix}.{secret}")


def _institution_scope_allows_revoke(
    principal: RequestPrincipal,
    record: ApplicationApiKey,
) -> bool:
    if principal.role == "org_admin" and principal.institution_id is None:
        return True
    return record.institution_id == principal.institution_id


def revoke_api_key(
    session: Session,
    *,
    principal: RequestPrincipal,
    key_id: str,
    correlation_id: str = "unknown",
) -> None:
    key_hex = canonical_id(key_id)
    record = session.scalar(
        select(ApplicationApiKey).where(
            ApplicationApiKey.id == key_hex,
            ApplicationApiKey.organization_id == principal.organization_id,
        )
    )
    if record is None:
        raise NotFoundError("API key not found")
    if not _institution_scope_allows_revoke(principal, record):
        raise NotFoundError("API key not found")
    is_owner = record.created_by_principal_id == principal.principal_id
    is_admin = "api_keys:manage" in principal.scopes
    if not is_owner and not is_admin:
        raise AuthorizationError("API key revocation denied")
    if not is_owner:
        require_permission(principal.scopes, "api_keys:manage")
    record.active = False
    record.revoked_at = datetime.now(UTC)
    record_security_event(
        session,
        event_type="auth.api_key.revoke",
        correlation_id=correlation_id,
        success=True,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        principal_id=principal.principal_id,
        metadata={"key_id": key_hex, "owner": is_owner, "admin": is_admin},
    )


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
    creator_id = record.created_by_principal_id
    if creator_id is None:
        raise AuthenticationError("API key missing owner")
    creator = load_and_validate_principal(session, creator_id)
    if not creator.active:
        raise AuthenticationError("API key owner disabled")
    if creator.organization_id != record.organization_id:
        raise AuthenticationError("API key owner no longer in key organization")
    if creator.institution_id != record.institution_id:
        raise AuthenticationError("API key owner institution no longer matches key binding")
    stored = [str(s) for s in record.scopes_json]
    role_allowed = delegatable_scopes_for_role(creator.role)
    scopes = assert_scopes_subset(stored, role_allowed)
    return request_principal_from_api_key(record, creator, scopes=scopes)