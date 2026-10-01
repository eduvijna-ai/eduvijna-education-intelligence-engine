from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.db.session import get_engine


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("x-request-id")


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_system_info(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "eduvijna-api"
    assert payload["status"] == "ok"
    assert payload["api_version"] == "v1"


def test_sqlite_engine_connects() -> None:
    with get_engine().connect() as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_settings_parse_cors() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_settings_rejects_short_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(api_secret_key="short")


def test_settings_reject_default_secret_outside_local() -> None:
    with pytest.raises(ValidationError, match="API_SECRET_KEY"):
        Settings(app_env="production")


def test_settings_accept_explicit_non_local_secret() -> None:
    settings = Settings(app_env="production", api_secret_key="a-production-secret")
    assert settings.app_env == "production"
