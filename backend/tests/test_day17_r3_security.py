from __future__ import annotations

import app.models  # noqa: F401
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import create_database_engine, get_settings, session_factory
from app.main import app
from app.platform.auth.service import bootstrap_principal
from app.platform.auth.tokens import decode_access_token
from tests.day17_fixtures import seed_admin, seed_tenant_with_teacher


def test_refresh_session_epoch_column_present(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'epoch.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    Base.metadata.create_all(engine := create_database_engine(db_url))

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
    assert login.status_code == 200
    tokens = login.json()
    claims = decode_access_token(tokens["access_token"])
    assert claims.session_epoch >= 0

    logout = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 204
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 401


def test_api_key_binds_stored_tenant_not_moved_creator(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'keybind.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    Base.metadata.create_all(create_database_engine(db_url))

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
    token = login.json()["access_token"]
    created = client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "bind-test", "scopes": ["capabilities:read", "jobs:read"]},
    )
    assert created.status_code == 201
    secret = created.json()["secret"]
    caps = client.get("/api/v1/capabilities", headers={"X-API-Key": secret})
    assert caps.status_code == 200