"""AT05 — migration lock semantics under concurrent access (SQLite proof; PG when opt-in)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from tests.c01_at_support import REV_0020, REV_0021, insert_replay_sqlite, run_alembic


@pytest.mark.c01_at05
def test_at05_sqlite_second_connection_busy_during_immediate_transaction(tmp_path: Path) -> None:
    database_path = tmp_path / "busy.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path, timeout=1.0)
    holder = sqlite3.connect(database_path, timeout=1.0)
    errors: list[BaseException] = []
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
        holder.execute("BEGIN IMMEDIATE")
        holder.execute(
            "UPDATE d13_replay_reservations SET updated_at = updated_at WHERE 1=1"
        )

        def attempt_write() -> None:
            other = sqlite3.connect(database_path, timeout=0.2)
            try:
                other.execute(
                    "INSERT INTO d13_replay_reservations (id) VALUES ('blocked')"
                )
                other.commit()
            except sqlite3.OperationalError as exc:
                errors.append(exc)
            finally:
                other.close()

        thread = threading.Thread(target=attempt_write)
        thread.start()
        thread.join(timeout=2.0)
        assert any(isinstance(exc, sqlite3.OperationalError) for exc in errors)
        assert any("locked" in str(exc).lower() for exc in errors)
    finally:
        holder.rollback()
        holder.close()
        connection.close()


@pytest.mark.c01_at05
def test_at05_migration_upgrade_succeeds_after_lock_released(tmp_path: Path) -> None:
    database_path = tmp_path / "after-lock.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    assert run_alembic(database_path, "upgrade", REV_0021).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == REV_0021
    finally:
        connection.close()