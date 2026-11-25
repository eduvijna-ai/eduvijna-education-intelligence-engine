"""Validate principal membership against canonical tenancy actors."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_auth import ApplicationPrincipal
from app.models.tenancy import AdminActor, Institution, Organization, Teacher
from app.platform.errors import AuthenticationError, AuthorizationError


def validate_principal_membership(session: Session, principal: ApplicationPrincipal) -> None:
    if principal.learner_id:
        raise AuthenticationError("Learner application principals are not enabled (Day15 hold)")
    if principal.role == "teacher":
        if not principal.teacher_id or principal.admin_actor_id:
            raise AuthenticationError("Teacher role requires an active teacher actor binding")
    elif principal.role == "institution_admin":
        if not principal.admin_actor_id or principal.teacher_id:
            raise AuthenticationError("Institution admin requires an active admin actor binding")
    elif principal.role == "org_admin":
        if principal.institution_id is not None:
            raise AuthenticationError("Organization admin must be org-scoped without institution")
        if not principal.admin_actor_id or principal.teacher_id:
            raise AuthenticationError("Organization admin requires an admin actor binding")
    else:
        raise AuthenticationError(f"Unsupported application role: {principal.role}")

    org = session.scalar(
        select(Organization).where(Organization.id == principal.organization_id)
    )
    if org is None or not org.active:
        raise AuthorizationError("Organization inactive or unknown")
    if principal.institution_id:
        inst = session.scalar(
            select(Institution).where(
                Institution.id == principal.institution_id,
                Institution.organization_id == principal.organization_id,
            )
        )
        if inst is None or not inst.active:
            raise AuthorizationError("Institution inactive or unknown")
    if principal.teacher_id:
        teacher = session.scalar(select(Teacher).where(Teacher.id == principal.teacher_id))
        if (
            teacher is None
            or not teacher.active
            or teacher.institution_id != principal.institution_id
        ):
            raise AuthenticationError("Teacher membership invalid")
        return
    if principal.admin_actor_id:
        admin = session.scalar(select(AdminActor).where(AdminActor.id == principal.admin_actor_id))
        if admin is None or not admin.active:
            raise AuthenticationError("Admin membership invalid")
        if admin.organization_id and admin.organization_id != principal.organization_id:
            raise AuthenticationError("Admin tenant mismatch")
        if (
            principal.institution_id
            and admin.institution_id
            and admin.institution_id != principal.institution_id
        ):
            raise AuthenticationError("Admin institution mismatch")
        return
    raise AuthenticationError("Principal has no bound actor")