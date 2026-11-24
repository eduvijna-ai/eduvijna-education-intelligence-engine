from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationApiKey, ApplicationPrincipal
from app.models.tenancy import Institution, Organization


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
