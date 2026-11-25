from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.tenancy import AdminActor, Institution, Organization, Teacher
from app.platform.auth.service import bootstrap_principal


def seed_tenant_with_teacher(session: Session) -> tuple[Organization, Institution, Teacher, str]:
    org = Organization(
        id=uuid.uuid4().hex,
        code="day17-org",
        name="Day17 Org",
        active=True,
    )
    inst = Institution(
        id=uuid.uuid4().hex,
        organization_id=org.id,
        code="day17-inst",
        name="Day17 Institution",
        active=True,
    )
    teacher = Teacher(
        id=uuid.uuid4().hex,
        institution_id=inst.id,
        external_code="t-001",
        display_name="Teacher One",
        active=True,
    )
    session.add(org)
    session.flush()
    session.add(inst)
    session.flush()
    session.add(teacher)
    session.flush()
    bootstrap_principal(
        session,
        organization=org,
        institution=inst,
        teacher=teacher,
        admin=None,
        login_code="teacher.login",
        password="correct-horse-battery",
        role="teacher",
    )
    session.flush()
    return org, inst, teacher, "correct-horse-battery"


def seed_admin(session: Session, org: Organization, inst: Institution) -> AdminActor:
    admin = AdminActor(
        id=uuid.uuid4().hex,
        organization_id=org.id,
        institution_id=inst.id,
        external_code="admin-001",
        display_name="Admin One",
        active=True,
    )
    session.add(admin)
    session.flush()
    return admin
