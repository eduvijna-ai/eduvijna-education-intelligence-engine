"""AT03 — unmodified 0020→0021 preflight on disposable populated fixtures."""

from __future__ import annotations

import sqlite3

import pytest

from migrations.c01_d13_synthetic_preflight import strict_eligible_from_raw
from tests.c01_at_support import (
    REV_0020,
    REV_0021,
    insert_replay_sqlite,
    replay_rows_digest,
    run_alembic,
    sqlite_schema_digest,
)


def test_at03_unit_strict_marker_rejects_hostile_json() -> None:
    assert strict_eligible_from_raw('{"d13_synthetic_test_only": true}') is True
    for raw in (
        "{}",
        '{"d13_synthetic_test_only": false}',
        '{"d13_synthetic_test_only": 1}',
        '{"d13_synthetic_test_only": "true"}',
        "null",
        "[]",
        '{"d13_synthetic_test_only": true, "d13_synthetic_test_only": false}',
        '{"a":{"d13_synthetic_test_only":true}}',
    ):
        assert strict_eligible_from_raw(raw) is False


@pytest.mark.c01_at03
def test_at03_invalid_fixture_stays_at_0020_with_unchanged_digests(tmp_path) -> None:
    database_path = tmp_path / "hostile.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        insert_replay_sqlite(connection, metadata="{}")
        connection.commit()
        before_rows = replay_rows_digest(connection)
        before_schema = sqlite_schema_digest(connection)
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
        assert replay_rows_digest(connection) == before_rows
        assert sqlite_schema_digest(connection) == before_schema
    finally:
        connection.close()


@pytest.mark.c01_at03
def test_at03_valid_fixture_preserves_rows_and_adds_true_flag_only(tmp_path) -> None:
    database_path = tmp_path / "valid.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        row_id = insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
        before_cols = connection.execute(
            "SELECT id, metadata_json FROM d13_replay_reservations WHERE id = ?",
            (row_id,),
        ).fetchone()
    finally:
        connection.close()

    assert run_alembic(database_path, "upgrade", REV_0021).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        after = connection.execute(
            "SELECT id, metadata_json, synthetic_test_only "
            "FROM d13_replay_reservations WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert after[0] == before_cols[0]
        assert after[1] == before_cols[1]
        assert after[2] == 1
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == REV_0021
    finally:
        connection.close()


@pytest.mark.c01_at03
def test_at03_rejects_inconsistent_replay_state(tmp_path) -> None:
    database_path = tmp_path / "state.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(
            connection,
            metadata='{"d13_synthetic_test_only": true}',
            reservation_state="reserved",
            owner_token=None,
        )
        connection.commit()
    finally:
        connection.close()
    failed = run_alembic(database_path, "upgrade", REV_0021, check=False)
    assert failed.returncode != 0
    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == REV_0020
    finally:
        connection.close()