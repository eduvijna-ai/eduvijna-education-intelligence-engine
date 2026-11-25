from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationPrincipal, ApplicationRefreshSession
from app.models.tenancy import AdminActor, Institution, Organization, Teacher
from app.platform.auth.audit import record_security_event
from app.platform.auth.membership import validate_principal_membership
from app.platform.auth.passwords import hash_password, verify_password
from app.platform.auth.principal import (
    RequestPrincipal,
    assert_tenant_active,
    load_and_validate_principal,
    request_principal_from_application,
    resolve_actor_ref,
)
from app.platform.auth.rbac import scopes_for_role
from app.platform.auth.session_epoch import bump_session_epoch, read_session_epoch
from app.platform.auth.tokens import (
    REFRESH_TOKEN_TTL_SECONDS,
    build_access_claims,
    decode_access_token,
    hash_refresh_token,
    issue_refresh_token,
)
from app.platform.errors import AuthenticationError, AuthorizationError


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


def _flush_audit(session: Session) -> None:
    session.flush()


def bootstrap_principal(
    session: Session,
    *,
    organization: Organization,
    institution: Institution | None,
    teacher: Teacher | None,
    admin: AdminActor | None,
    login_code: str,
    password: str,
    role: str,
) -> ApplicationPrincipal:
    principal = ApplicationPrincipal(
        id=uuid.uuid4().hex,
        organization_id=organization.id,
        institution_id=institution.id if institution else None,
        teacher_id=teacher.id if teacher else None,
        learner_id=None,
        admin_actor_id=admin.id if admin else None,
        login_code=login_code,
        display_name=(
            teacher.display_name if teacher else (admin.display_name if admin else login_code)
        ),
        role=role,
        password_hash_json=hash_password(password),
        active=True,
        metadata_json={"session_epoch": 0},
    )
    session.add(principal)
    session.flush()
    validate_principal_membership(session, principal)
    return principal


def login(
    session: Session,
    *,
    organization_code: str,
    login_code: str,
    password: str,
    correlation_id: str,
) -> tuple[AuthTokens, RequestPrincipal]:
    org = session.scalar(select(Organization).where(Organization.code == organization_code))
    if org is None or not org.active:
        record_security_event(
            session,
            event_type="auth.login",
            correlation_id=correlation_id,
            success=False,
            metadata={"reason": "unknown_org"},
        )
        _flush_audit(session)
        raise AuthenticationError("Invalid credentials")
    principal = session.scalar(
        select(ApplicationPrincipal).where(
            ApplicationPrincipal.organization_id == org.id,
            ApplicationPrincipal.login_code == login_code,
        )
    )
    if principal is None or not principal.active:
        record_security_event(
            session,
            event_type="auth.login",
            correlation_id=correlation_id,
            success=False,
            organization_id=org.id,
        )
        _flush_audit(session)
        raise AuthenticationError("Invalid credentials")
    if not verify_password(password, principal.password_hash_json):
        record_security_event(
            session,
            event_type="auth.login",
            correlation_id=correlation_id,
            success=False,
            organization_id=org.id,
            principal_id=principal.id,
        )
        _flush_audit(session)
        raise AuthenticationError("Invalid credentials")
    validate_principal_membership(session, principal)
    assert_tenant_active(session, principal.organization_id, principal.institution_id)
    tokens, request_principal = _issue_session_tokens(session, principal)
    record_security_event(
        session,
        event_type="auth.login",
        correlation_id=correlation_id,
        success=True,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        principal_id=principal.id,
    )
    return tokens, request_principal


def refresh(
    session: Session,
    *,
    refresh_token: str,
    correlation_id: str,
) -> AuthTokens:
    token_hash = hash_refresh_token(refresh_token)
    peek = session.scalar(
        select(ApplicationRefreshSession).where(ApplicationRefreshSession.token_hash == token_hash)
    )
    if peek is None or peek.revoked_at is not None:
        record_security_event(
            session,
            event_type="auth.refresh",
            correlation_id=correlation_id,
            success=False,
        )
        _flush_audit(session)
        raise AuthenticationError("Invalid refresh token")
    expires_at = peek.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        record_security_event(
            session,
            event_type="auth.refresh",
            correlation_id=correlation_id,
            success=False,
            principal_id=peek.principal_id,
        )
        _flush_audit(session)
        raise AuthenticationError("Refresh token expired")
    principal = load_and_validate_principal(session, peek.principal_id)
    current_epoch = read_session_epoch(principal)
    if peek.session_epoch != current_epoch:
        record_security_event(
            session,
            event_type="auth.refresh",
            correlation_id=correlation_id,
            success=False,
            principal_id=peek.principal_id,
        )
        _flush_audit(session)
        raise AuthenticationError("Refresh session revoked")
    now = datetime.now(UTC)
    rotated = session.execute(
        update(ApplicationRefreshSession)
        .where(
            ApplicationRefreshSession.id == peek.id,
            ApplicationRefreshSession.token_hash == token_hash,
            ApplicationRefreshSession.revoked_at.is_(None),
            ApplicationRefreshSession.session_epoch == current_epoch,
        )
        .values(revoked_at=now)
    )
    if getattr(rotated, "rowcount", 0) != 1:
        record_security_event(
            session,
            event_type="auth.refresh",
            correlation_id=correlation_id,
            success=False,
            principal_id=peek.principal_id,
        )
        _flush_audit(session)
        raise AuthenticationError("Invalid refresh token")
    tokens, _ = _issue_session_tokens(
        session, principal, family_id=peek.family_id, replaced_by_rotation=True
    )
    record_security_event(
        session,
        event_type="auth.refresh",
        correlation_id=correlation_id,
        success=True,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        principal_id=principal.id,
    )
    return tokens


def logout(session: Session, *, refresh_token: str, correlation_id: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    row = session.scalar(
        select(ApplicationRefreshSession)
        .where(ApplicationRefreshSession.token_hash == token_hash)
        .with_for_update()
    )
    principal_id: str | None = None
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        principal_id = row.principal_id
        principal = session.scalar(
            select(ApplicationPrincipal).where(ApplicationPrincipal.id == row.principal_id)
        )
        if principal is not None:
            bump_session_epoch(session, principal)
    record_security_event(
        session,
        event_type="auth.logout",
        correlation_id=correlation_id,
        success=True,
        principal_id=principal_id,
    )


def principal_from_access_token(session: Session, token: str) -> RequestPrincipal:
    try:
        claims = decode_access_token(token)
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc
    principal = load_and_validate_principal(session, claims.sub)
    if principal.organization_id != claims.organization_id:
        raise AuthenticationError("Token tenant mismatch")
    if principal.institution_id != claims.institution_id:
        raise AuthenticationError("Token institution mismatch")
    if read_session_epoch(principal) != claims.session_epoch:
        raise AuthenticationError("Access token revoked")
    actor_kind, actor_ref = resolve_actor_ref(principal)
    if claims.role != principal.role:
        raise AuthenticationError("Token role stale")
    if claims.actor_kind != actor_kind or claims.actor_ref != actor_ref:
        raise AuthenticationError("Token actor stale")
    scopes = tuple(sorted(scopes_for_role(principal.role)))
    return request_principal_from_application(
        principal,
        auth_method="bearer",
        scopes=scopes,
        actor_kind=actor_kind,
        actor_ref=actor_ref,
    )


def _issue_session_tokens(
    session: Session,
    principal: ApplicationPrincipal,
    *,
    family_id: str | None = None,
    replaced_by_rotation: bool = False,
) -> tuple[AuthTokens, RequestPrincipal]:
    actor_kind, actor_ref = resolve_actor_ref(principal)
    scopes = tuple(sorted(scopes_for_role(principal.role)))
    epoch = read_session_epoch(principal)
    _, access_token = build_access_claims(
        principal_id=principal.id,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        role=principal.role,
        scopes=scopes,
        actor_kind=actor_kind,
        actor_ref=actor_ref,
        session_epoch=epoch,
    )
    refresh_raw = issue_refresh_token()
    family = family_id or uuid.uuid4().hex
    session_row = ApplicationRefreshSession(
        id=uuid.uuid4().hex,
        principal_id=principal.id,
        token_hash=hash_refresh_token(refresh_raw),
        family_id=family,
        expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        session_epoch=epoch,
    )
    session.add(session_row)
    request_principal = request_principal_from_application(
        principal,
        auth_method="bearer",
        scopes=scopes,
        actor_kind=actor_kind,
        actor_ref=actor_ref,
    )
    _ = replaced_by_rotation
    return AuthTokens(access_token=access_token, refresh_token=refresh_raw), request_principal


def change_password(
    session: Session,
    *,
    principal: RequestPrincipal,
    current_password: str,
    new_password: str,
) -> None:
    row = session.scalar(
        select(ApplicationPrincipal).where(ApplicationPrincipal.id == principal.principal_id)
    )
    if row is None:
        raise AuthenticationError("Principal not found")
    if row.role != principal.role:
        raise AuthorizationError("Role escalation denied")
    if not verify_password(current_password, row.password_hash_json):
        raise AuthenticationError("Invalid current password")
    row.password_hash_json = hash_password(new_password)
    bump_session_epoch(session, row)