from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test-eduvijna.db")

from app.core.config import get_settings  # noqa: E402
from app.db.session import create_database_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    yield
    get_settings.cache_clear()
    create_database_engine.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
