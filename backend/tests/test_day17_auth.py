from __future__ import annotations

from fastapi.testclient import TestClient

import app.models  # noqa: F401 — register ORM metadata for create_all
from app.db.base import Base
from app.db.session import create_database_engine, get_settings
from app.main import app
from app.platform.auth.rbac import ROLE_PERMISSIONS
from app.platform.auth.service import bootstrap_principal
from app.platform.auth.tokens import decode_access_token
from tests.day17_fixtures import seed_admin, seed_tenant_with_teacher


def _bootstrap_db(database_url: str) -> None:
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)


def test_login_refresh_logout_and_me(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    _bootstrap_db(db_url)

    from app.db.session import session_factory

    session = session_factory()()
    try:
        org, _, _, password = seed_tenant_with_teacher(session)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_code": org.code,
            "login_code": "teacher.login",
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    claims = decode_access_token(tokens["access_token"])
    assert claims.organization_id

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "teacher"

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert logout.status_code == 204

    bad = client.post(
        "/api/v1/auth/login",
        json={
            "organization_code": org.code,
            "login_code": "teacher.login",
            "password": "wrong-password-xyz",
        },
    )
    assert bad.status_code == 401


def test_api_key_create_and_use(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'key.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    _bootstrap_db(db_url)

    from app.db.session import session_factory

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
    assert login.status_code == 200
    token = login.json()["access_token"]
    created = client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "ci-key", "scopes": sorted(ROLE_PERMISSIONS["teacher"])},
    )
    assert created.status_code == 201, created.text
    secret = created.json()["secret"]
    caps = client.get("/api/v1/capabilities", headers={"X-API-Key": secret})
    assert caps.status_code == 200
