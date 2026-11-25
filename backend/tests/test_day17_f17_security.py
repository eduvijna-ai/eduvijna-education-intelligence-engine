from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine, get_settings, session_factory
from app.main import app
from app.platform.auth.rbac import ROLE_PERMISSIONS
from app.platform.auth.service import bootstrap_principal
from app.platform.errors import AuthorizationError
from app.platform.ids import canonical_id
from app.platform.jobs.internal_harness import enqueue_internal_synthetic_fixture
from tests.day17_fixtures import seed_admin, seed_tenant_with_teacher


def _bootstrap(database_url: str) -> None:
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)


def test_teacher_cannot_mint_admin_scopes(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'scope.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    _bootstrap(db_url)

    session = session_factory()()
    try:
        org, _, _, password = seed_tenant_with_teacher(session)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"organization_code": org.code, "login_code": "teacher.login", "password": password},
    )
    token = login.json()["access_token"]
    resp = client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "escalation", "scopes": ["api_keys:manage"]},
    )
    assert resp.status_code == 403


def test_logout_invalidates_access_token(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'logout.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    _bootstrap(db_url)

    session = session_factory()()
    try:
        org, _, _, password = seed_tenant_with_teacher(session)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"organization_code": org.code, "login_code": "teacher.login", "password": password},
    )
    body = login.json()
    access = body["access_token"]
    client.post("/api/v1/auth/logout", json={"refresh_token": body["refresh_token"]})
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 401


def test_job_id_scoped_by_owner(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'job.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    _bootstrap(db_url)

    session = session_factory()()
    try:
        org, inst, _, _ = seed_tenant_with_teacher(session)
        admin = seed_admin(session, org, inst)
        bootstrap_principal(
            session,
            organization=org,
            institution=inst,
            teacher=None,
            admin=admin,
            login_code="admin.login",
            password="admin-password-123456",
            role="institution_admin",
        )
        session.commit()

        from sqlalchemy import select

        from app.models.platform_auth import ApplicationPrincipal

        teacher_row = session.scalar(
            select(ApplicationPrincipal).where(ApplicationPrincipal.login_code == "teacher.login")
        )
        admin_row = session.scalar(
            select(ApplicationPrincipal).where(ApplicationPrincipal.login_code == "admin.login")
        )
        assert teacher_row and admin_row

        from app.platform.auth.principal import RequestPrincipal

        teacher_principal = RequestPrincipal(
            principal_id=teacher_row.id,
            organization_id=org.id,
            institution_id=inst.id,
            role="teacher",
            scopes=tuple(sorted(ROLE_PERMISSIONS["teacher"])),
            actor_kind="teacher",
            actor_ref=teacher_row.teacher_id or "",
            auth_method="bearer",
        )
        job = enqueue_internal_synthetic_fixture(
            session, principal=teacher_principal, idempotency_key="scoped-1"
        )
        session.commit()
        job_uuid = f"{job.id[:8]}-{job.id[8:12]}-{job.id[12:16]}-{job.id[16:20]}-{job.id[20:]}"
    finally:
        session.close()

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_code": org.code,
            "login_code": "admin.login",
            "password": "admin-password-123456",
        },
    )
    token = login.json()["access_token"]
    resp = client.get(f"/api/v1/jobs/{job_uuid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_uuid_lookup_accepts_hyphenated(tmp_path, monkeypatch) -> None:
    value = "550e8400-e29b-41d4-a716-446655440000"
    assert canonical_id(value) == value.replace("-", "")


def test_delegate_subset_enforced() -> None:
    from app.platform.auth.delegation import assert_scopes_subset, delegatable_scopes_for_role

    with pytest.raises(AuthorizationError):
        assert_scopes_subset(["api_keys:manage"], delegatable_scopes_for_role("teacher"))