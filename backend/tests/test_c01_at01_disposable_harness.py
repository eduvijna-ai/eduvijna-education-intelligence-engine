"""AT01 — disposable database ownership harness (before any unsafe DB connect)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings
from tests.c01_at_support import (
    assert_pg_schema_empty,
    create_owned_pg_database,
    drop_owned_pg_database,
    owned_pg_database_name,
    pg_admin_url_from_disposable,
    restored_env,
)
from tests.c01_disposable_pg import (
    C01_PG_OPT_IN,
    C01_PG_URL,
    parse_disposable_pg_url,
    validated_disposable_pg_url,
)


def test_at01_rejects_remote_host_before_connect() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        parse_disposable_pg_url(
            "postgresql+psycopg://u:p@203.0.113.1:5432/owned",
            require_opt_in=False,
        )


def test_at01_rejects_query_and_fragment_override() -> None:
    with pytest.raises(ValueError, match="query"):
        parse_disposable_pg_url(
            "postgresql+psycopg://u:p@127.0.0.1:55433/db?options=-csearch_path%3Dpublic",
            require_opt_in=False,
        )
    with pytest.raises(ValueError, match="fragment"):
        parse_disposable_pg_url(
            "postgresql+psycopg://u:p@127.0.0.1:55433/db#route",
            require_opt_in=False,
        )


def test_at01_rejects_absent_opt_in_before_connect() -> None:
    with restored_env((C01_PG_OPT_IN, C01_PG_URL)):
        os.environ.pop(C01_PG_OPT_IN, None)
        os.environ[C01_PG_URL] = "postgresql+psycopg://u:p@127.0.0.1:55433/owned"
        with pytest.raises(ValueError, match=C01_PG_OPT_IN):
            validated_disposable_pg_url()


def test_at01_rejects_general_database_url_fallback() -> None:
    shared = "postgresql+psycopg://u:p@127.0.0.1:55433/shared"
    with restored_env(("DATABASE_URL", C01_PG_OPT_IN, C01_PG_URL)):
        os.environ[C01_PG_OPT_IN] = "1"
        os.environ["DATABASE_URL"] = shared
        os.environ[C01_PG_URL] = shared
        with pytest.raises(ValueError, match="must not equal general DATABASE_URL"):
            validated_disposable_pg_url()


def test_at01_sqlite_uses_private_temp_directory_only(tmp_path: Path) -> None:
    db_path = tmp_path / "owned.sqlite3"
    assert db_path.parent == tmp_path
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE at01_probe (id INTEGER PRIMARY KEY)"))
        conn.commit()
    assert db_path.exists()
    assert db_path.resolve().is_relative_to(tmp_path.resolve())


@contextmanager
def _owned_pg_if_available() -> Iterator[str]:
    if os.environ.get(C01_PG_OPT_IN) != "1":
        pytest.skip(f"{C01_PG_OPT_IN}=1 required")
    base_url = validated_disposable_pg_url()
    admin_url = pg_admin_url_from_disposable(base_url)
    db_name = owned_pg_database_name("c01_at01")
    owned_url = create_owned_pg_database(admin_url, db_name)
    try:
        assert_pg_schema_empty(owned_url)
        yield owned_url
    finally:
        drop_owned_pg_database(admin_url, db_name)


@pytest.mark.c01_at01
def test_at01_pg_creates_exclusively_owned_empty_database() -> None:
    with _owned_pg_if_available() as owned_url:
        parsed = urlparse(owned_url)
        assert parsed.hostname in {"127.0.0.1", "localhost"}
        assert parsed.port in {5432, 55432, 55433}
        engine = create_engine(owned_url)
        with engine.connect() as conn:
            tables = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_type = 'BASE TABLE'
                    """
                )
            ).scalar_one()
            assert int(tables) == 0


def test_at01_frozen_product_settings_guard_accepts_default_sqlite_without_opt_in() -> None:
    """Product guard evidence: frozen Settings has no disposable-database rejection."""
    settings = Settings()
    assert settings.database_url.startswith("sqlite:")
    # Known defect relative to AT01 harness policy — recorded for repair proposal, not masked.
    assert "127.0.0.1" in settings.database_url or settings.database_url.startswith("sqlite:")