"""C01 Gate B: portable 0006 / 0021 migration proof on disposable databases."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.migration_test_support import (
    alembic_executable,
    backend_root,
    repository_alembic_head,
    run_alembic,
)

REV_0020 = "20261124_0020"
REV_0021 = "20261124_0021"
REV_0006 = "20261003_0006"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_replay(connection: sqlite3.Connection, *, metadata: str) -> None:
    row_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO d13_replay_reservations (
            id, created_at, updated_at, organization_id, institution_id,
            exam_pack_code, exam_version_id, academic_year,
            idempotency_key_hash, request_fingerprint, reservation_state,
            metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            row_id,
            _now(),
            _now(),
            "org",
            "inst",
            "pack",
            str(uuid.uuid4()),
            "2026",
            "a" * 64,
            "b" * 64,
            "reserved",
            metadata,
        ),
    )


def test_sqlite_fresh_upgrade_head(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.db"
    result = run_alembic(database_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == repository_alembic_head()
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_sqlite_0021_preflight_rejects_non_strict_marker(tmp_path: Path) -> None:
    database_path = tmp_path / "mixed.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        _insert_replay(connection, metadata='{"d13_synthetic_test_only": true}')
        _insert_replay(connection, metadata="{}")
        connection.commit()
    finally:
        connection.close()

    failed = run_alembic(database_path, "upgrade", REV_0021, check=False)
    assert failed.returncode != 0
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == REV_0020
        cols = [row[1] for row in connection.execute("PRAGMA table_info(d13_replay_reservations)")]
        assert "synthetic_test_only" not in cols
    finally:
        connection.close()


def test_sqlite_0021_succeeds_with_strict_markers(tmp_path: Path) -> None:
    database_path = tmp_path / "strict.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        _insert_replay(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()

    run_alembic(database_path, "upgrade", REV_0021)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == REV_0021
        flag = connection.execute(
            "SELECT synthetic_test_only FROM d13_replay_reservations"
        ).fetchone()[0]
        assert flag in (1, True)
    finally:
        connection.close()


def test_sqlite_active_slot_check_after_0006(tmp_path: Path) -> None:
    from migrations.c01_constraints import SOURCE_REVISION_ACTIVE_SLOT_CHECK

    database_path = tmp_path / "slot.db"
    run_alembic(database_path, "upgrade", REV_0006)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            f"""
            CREATE TABLE c01_slot_probe (
              id INTEGER PRIMARY KEY,
              source_id INT NOT NULL,
              status TEXT NOT NULL,
              active_slot INT,
              CHECK ({SOURCE_REVISION_ACTIVE_SLOT_CHECK}),
              UNIQUE(source_id, active_slot)
            )
            """
        )
        connection.execute(
            "INSERT INTO c01_slot_probe VALUES (1, 1, 'active', 1)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO c01_slot_probe VALUES (2, 1, 'active', 2)")
            connection.commit()
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="Set DATABASE_URL to disposable PostgreSQL to run PG migration proof",
)
def test_postgresql_fresh_upgrade_head(tmp_path: Path) -> None:
    url = os.environ["DATABASE_URL"]
    result = run_alembic_with_url(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr + result.stdout


def run_alembic_with_url(database_url: str, *args: str, check: bool = True):
    import subprocess

    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [alembic_executable(), "-c", str(backend_root() / "alembic.ini"), *args],
        cwd=backend_root(),
        env=environment,
        check=check,
        capture_output=True,
        text=True,
    )


def test_preflight_unit_rejects_int_marker() -> None:
    from migrations.c01_d13_synthetic_preflight import strict_eligible_from_raw

    assert strict_eligible_from_raw('{"d13_synthetic_test_only": true}') is True
    assert strict_eligible_from_raw('{"d13_synthetic_test_only": 1}') is False
    assert strict_eligible_from_raw('{"d13_synthetic_test_only": "true"}') is False
    assert (
        strict_eligible_from_raw(
            '{"d13_synthetic_test_only": false, "d13_synthetic_test_only": true}'
        )
        is False
    )