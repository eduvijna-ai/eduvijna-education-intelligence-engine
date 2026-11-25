from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine, get_settings
from app.main import app
from tests.day17_fixtures import seed_tenant_with_teacher


def test_blocked_learner_and_remediation_paths(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'blocked.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    engine = create_database_engine(db_url)
    Base.metadata.create_all(engine)

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
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    learner_id = uuid.uuid4()
    for path in (
        f"/api/v1/learners/{learner_id}/mastery",
        f"/api/v1/learners/{learner_id}/diagnostics",
    ):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "CAPABILITY_NOT_READY"

    rem = client.post(
        f"/api/v1/learners/{learner_id}/remediation",
        headers=headers,
        json={"diagnostic_ref": "synthetic"},
    )
    assert rem.status_code == 503

    gen = client.post(
        "/api/v1/questions/generate",
        headers=headers,
        json={
            "topic_code": "algebra",
            "count": 5,
            "idempotency_key": "idem-test-1",
        },
    )
    assert gen.status_code in {403, 503}
    if gen.status_code == 503:
        assert gen.json()["error"]["code"] == "CAPABILITY_NOT_READY"
