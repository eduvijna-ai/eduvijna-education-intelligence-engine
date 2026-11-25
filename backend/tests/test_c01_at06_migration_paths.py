"""AT06 — fresh head upgrades and populated historical chains."""

from __future__ import annotations

import sqlite3

import pytest

from tests.c01_at_support import (
    REV_0005,
    REV_0006,
    REV_0018,
    REV_0020,
    REV_0021,
    insert_replay_sqlite,
    repository_alembic_head,
)
from tests.migration_test_support import run_alembic as migration_run


@pytest.mark.c01_at06
def test_at06_sqlite_fresh_empty_upgrade_head(tmp_path) -> None:
    database_path = tmp_path / "fresh.db"
    result = migration_run(database_path, "upgrade", "head")
    assert result.returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == repository_alembic_head()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.c01_at06
def test_at06_populated_0018_to_0021_chain(tmp_path) -> None:
    database_path = tmp_path / "pop21.db"
    migration_run(database_path, "upgrade", REV_0018)
    migration_run(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    migration_run(database_path, "upgrade", REV_0021)
    assert migration_run(database_path, "check", check=False).returncode == 0


@pytest.mark.c01_at06
def test_at06_legacy_0005_to_0006_path_upgrades(tmp_path) -> None:
    database_path = tmp_path / "d3.db"
    migration_run(database_path, "upgrade", REV_0005)
    migration_run(database_path, "upgrade", REV_0006)
    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == REV_0006
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_revisions'"
        ).fetchone()[0]
        assert "active_slot IS NOT NULL AND active_slot = 1" in ddl
    finally:
        connection.close()