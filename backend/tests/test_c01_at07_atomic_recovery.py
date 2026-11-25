"""AT07 — downgrade/re-upgrade and integrity checks on disposable fixtures."""

from __future__ import annotations

import sqlite3

import pytest

from tests.c01_at_support import REV_0006, REV_0020, REV_0021, insert_replay_sqlite
from tests.migration_test_support import run_alembic as migration_run


@pytest.mark.c01_at07
def test_at07_sqlite_0021_downgrade_reupgrade_preserves_replay_metadata(tmp_path) -> None:
    database_path = tmp_path / "reup.db"
    migration_run(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        row_id = insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
        meta_before = connection.execute(
            "SELECT metadata_json FROM d13_replay_reservations WHERE id = ?",
            (row_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    migration_run(database_path, "upgrade", REV_0021)
    migration_run(database_path, "downgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        cols = [row[1] for row in connection.execute("PRAGMA table_info(d13_replay_reservations)")]
        assert "synthetic_test_only" not in cols
        meta_after = connection.execute(
            "SELECT metadata_json FROM d13_replay_reservations WHERE id = ?",
            (row_id,),
        ).fetchone()[0]
        assert meta_after == meta_before
    finally:
        connection.close()
    migration_run(database_path, "upgrade", REV_0021)
    assert migration_run(database_path, "check", check=False).returncode == 0


@pytest.mark.c01_at07
def test_at07_sqlite_foreign_keys_restored_after_downgrade(tmp_path) -> None:
    database_path = tmp_path / "fk.db"
    migration_run(database_path, "upgrade", REV_0006)
    migration_run(database_path, "upgrade", REV_0021)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()