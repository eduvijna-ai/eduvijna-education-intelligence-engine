from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_engine, get_engine
from app.models import SystemSetting


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


def test_sqlite_data_survives_engine_reopen(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'persistence.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(SystemSetting(key="test.persistence", value="survives-reopen"))
        session.commit()

    engine.dispose()
    create_database_engine.cache_clear()

    reopened = create_database_engine(database_url)
    try:
        with Session(reopened) as session:
            row = session.query(SystemSetting).filter_by(key="test.persistence").one()
            assert row.value == "survives-reopen"
    finally:
        reopened.dispose()
        create_database_engine.cache_clear()


def test_settings_parse_cors() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_settings_rejects_short_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(api_secret_key="short")


@pytest.mark.parametrize(
    "placeholder",
    ["local-development-only", "change-me-for-non-local-use"],
)
def test_settings_rejects_shipped_placeholder_secret_outside_local(placeholder: str) -> None:
    with pytest.raises(ValidationError, match="API_SECRET_KEY"):
        Settings(app_env="production", api_secret_key=placeholder)


def test_settings_accept_explicit_non_local_secret() -> None:
    settings = Settings(app_env="production", api_secret_key="a-production-secret")
    assert settings.app_env == "production"


def test_domain_model_info(client: TestClient) -> None:
    response = client.get("/api/v1/system/domain-model")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "d02"
    assert "concept" in payload["curriculum_node_types"]
    assert "single_choice" in payload["question_types"]
    assert "official_syllabus" in payload["source_types"]
    assert "prerequisite_gap" in payload["diagnostic_categories"]
