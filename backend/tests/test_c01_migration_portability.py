"""C01 Gate B: portable 0006 / 0021 migration proof on disposable databases."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime
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
REV_0018 = "20261109_0018"
C01_PG_OPT_IN = "EDUVIJNA_C01_DISPOSABLE_PG"
C01_PG_URL = "EDUVIJNA_C01_DISPOSABLE_DATABASE_URL"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _insert_replay(connection: sqlite3.Connection, *, metadata: str) -> str:
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
    return row_id


def _disposable_pg_url() -> str | None:
    if os.environ.get(C01_PG_OPT_IN) != "1":
        return None
    url = os.environ.get(C01_PG_URL, "") or os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+")):
        return None
    disposable_markers = ("c01_ci", "c01_gate", "c01_diag", "127.0.0.1", "localhost")
    if not any(marker in url for marker in disposable_markers):
        return None
    return url


def run_alembic_with_url(database_url: str, *args: str, check: bool = True):
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


def test_sqlite_fresh_upgrade_head(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.db"
    result = run_alembic(database_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == repository_alembic_head()
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
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == REV_0020
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
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == REV_0021
        flag = connection.execute(
            "SELECT synthetic_test_only FROM d13_replay_reservations"
        ).fetchone()[0]
        assert flag == 1
    finally:
        connection.close()


def test_sqlite_synthetic_check_rejects_invalid_values(tmp_path: Path) -> None:
    database_path = tmp_path / "syn-check.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        row_id = _insert_replay(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)
    connection = sqlite3.connect(database_path)
    try:
        row_id = connection.execute("SELECT id FROM d13_replay_reservations LIMIT 1").fetchone()[0]
        for bad in (0, 2, -1):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE d13_replay_reservations SET synthetic_test_only = ? WHERE id = ?",
                    (bad, row_id),
                )
                connection.commit()
            connection.rollback()
    finally:
        connection.close()


def test_sqlite_source_revision_active_slot_on_real_table(tmp_path: Path) -> None:
    database_path = tmp_path / "src-slot.db"
    run_alembic(database_path, "upgrade", REV_0006)
    connection = sqlite3.connect(database_path)
    try:
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_revisions'"
        ).fetchone()[0]
        assert "active_slot IS NOT NULL AND active_slot = 1" in ddl
    finally:
        connection.close()


def test_sqlite_populated_chain_0018_to_0021(tmp_path: Path) -> None:
    database_path = tmp_path / "pop-21.db"
    run_alembic(database_path, "upgrade", REV_0018)
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        _insert_replay(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)
    assert run_alembic(database_path, "check", check=False).returncode == 0


def test_sqlite_0021_downgrade_reupgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "down.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        _insert_replay(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)
    run_alembic(database_path, "downgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        cols = [row[1] for row in connection.execute("PRAGMA table_info(d13_replay_reservations)")]
        assert "synthetic_test_only" not in cols
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)


@pytest.mark.skipif(
    os.environ.get(C01_PG_OPT_IN) != "1",
    reason=f"{C01_PG_OPT_IN}=1 required",
)
def test_postgresql_fresh_empty_upgrade_head() -> None:
    url = _disposable_pg_url()
    if url is None:
        pytest.skip("DATABASE_URL must point at disposable local PostgreSQL")
    result = run_alembic_with_url(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr + result.stdout


def test_preflight_unit_rejects_int_marker() -> None:
    from migrations.c01_d13_synthetic_preflight import strict_eligible_from_raw

    assert strict_eligible_from_raw('{"d13_synthetic_test_only": true}') is True
    assert strict_eligible_from_raw('{"d13_synthetic_test_only": 1}') is False
    assert strict_eligible_from_raw('{"d13_synthetic_test_only": "true"}') is False
    dup = '{"d13_synthetic_test_only": false, "d13_synthetic_test_only": true}'
    assert strict_eligible_from_raw(dup) is False