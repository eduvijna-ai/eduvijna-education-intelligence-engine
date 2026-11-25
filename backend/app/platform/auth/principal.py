from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationApiKey, ApplicationPrincipal
from app.models.tenancy import Institution, Organization
from app.platform.auth.membership import validate_principal_membership
from app.platform.auth.rbac import scopes_for_role


@dataclass(frozen=True, slots=True)
class RequestPrincipal:
    principal_id: str
    organization_id: str
    institution_id: str | None
    role: str
    scopes: tuple[str, ...]
    actor_kind: str
    actor_ref: str
    auth_method: str


def resolve_actor_ref(principal: ApplicationPrincipal) -> tuple[str, str]:
    if principal.teacher_id:
        return "teacher", principal.teacher_id
    if principal.learner_id:
        return "learner", principal.learner_id
    if principal.admin_actor_id:
        return "admin", principal.admin_actor_id
    return "unknown", ""


def load_principal(session: Session, principal_id: str) -> ApplicationPrincipal | None:
    return session.scalar(
        select(ApplicationPrincipal).where(ApplicationPrincipal.id == principal_id)
    )


def assert_tenant_active(
    session: Session,
    organization_id: str,
    institution_id: str | None,
) -> None:
    org = session.scalar(select(Organization).where(Organization.id == organization_id))
    if org is None or not org.active:
        from app.platform.errors import AuthorizationError

        raise AuthorizationError("Organization inactive or unknown")
    if institution_id is None:
        return
    inst = session.scalar(
        select(Institution).where(
            Institution.id == institution_id,
            Institution.organization_id == organization_id,
        )
    )
    if inst is None or not inst.active:
        from app.platform.errors import AuthorizationError

        raise AuthorizationError("Institution inactive or unknown")


def api_key_scopes(record: ApplicationApiKey) -> tuple[str, ...]:
    return tuple(str(s) for s in record.scopes_json)


def request_principal_from_application(
    principal: ApplicationPrincipal,
    *,
    auth_method: str,
    scopes: tuple[str, ...] | None = None,
    actor_kind: str | None = None,
    actor_ref: str | None = None,
) -> RequestPrincipal:
    kind, ref = resolve_actor_ref(principal)
    effective_scopes = (
        scopes if scopes is not None else tuple(sorted(scopes_for_role(principal.role)))
    )
    return RequestPrincipal(
        principal_id=principal.id,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        role=principal.role,
        scopes=effective_scopes,
        actor_kind=actor_kind or kind,
        actor_ref=actor_ref or ref,
        auth_method=auth_method,
    )


def request_principal_from_api_key(
    record: ApplicationApiKey,
    creator: ApplicationPrincipal,
    *,
    scopes: tuple[str, ...],
) -> RequestPrincipal:
    return RequestPrincipal(
        principal_id=creator.id,
        organization_id=record.organization_id,
        institution_id=record.institution_id,
        role=creator.role,
        scopes=scopes,
        actor_kind="api_key",
        actor_ref=record.id,
        auth_method="api_key",
    )


def load_and_validate_principal(session: Session, principal_id: str) -> ApplicationPrincipal:
    principal = load_principal(session, principal_id)
    if principal is None or not principal.active:
        from app.platform.errors import AuthenticationError

        raise AuthenticationError("Principal inactive")
    assert_tenant_active(session, principal.organization_id, principal.institution_id)
    validate_principal_membership(session, principal)
    return principal
