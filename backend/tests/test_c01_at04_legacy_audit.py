"""AT04 — frozen audit_legacy_0021_state on read-only synthetic fixtures."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine

from migrations.c01_d13_synthetic_preflight import LegacyAuditStatus, audit_legacy_0021_state
from tests.c01_at_support import REV_0020, REV_0021, insert_replay_sqlite, run_alembic


def _audit_db(path) -> LegacyAuditStatus:
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        return audit_legacy_0021_state(conn).status


@pytest.mark.c01_at04
def test_at04_valid_post_0021_fixture_may_be_clean(tmp_path) -> None:
    database_path = tmp_path / "clean.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)
    assert _audit_db(database_path) == LegacyAuditStatus.CLEAN


@pytest.mark.c01_at04
def test_at04_column_absent_at_0020(tmp_path) -> None:
    database_path = tmp_path / "absent.db"
    run_alembic(database_path, "upgrade", REV_0020)
    assert _audit_db(database_path) == LegacyAuditStatus.COLUMN_ABSENT


@pytest.mark.c01_at04
def test_at04_wrong_revision_when_column_manually_present(tmp_path) -> None:
    database_path = tmp_path / "wrong-rev.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "ALTER TABLE d13_replay_reservations ADD COLUMN synthetic_test_only "
            "BOOLEAN NOT NULL DEFAULT 0"
        )
        connection.commit()
    finally:
        connection.close()
    assert _audit_db(database_path) == LegacyAuditStatus.WRONG_REVISION


@pytest.mark.c01_at04
def test_at04_version_row_invalid_zero_or_many(tmp_path) -> None:
    database_path = tmp_path / "ver.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM alembic_version")
        connection.commit()
    finally:
        connection.close()
    assert _audit_db(database_path) == LegacyAuditStatus.VERSION_ROW_INVALID

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("INSERT INTO alembic_version (version_num) VALUES ('x'), ('y')")
        connection.commit()
    finally:
        connection.close()
    assert _audit_db(database_path) == LegacyAuditStatus.VERSION_ROW_INVALID


@pytest.mark.c01_at04
def test_at04_untrusted_flags_for_legacy_integer_promotion(tmp_path) -> None:
    database_path = tmp_path / "untrusted.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)
    connection = sqlite3.connect(database_path)
    try:
        row_id = connection.execute("SELECT id FROM d13_replay_reservations LIMIT 1").fetchone()[0]
        connection.execute(
            "UPDATE d13_replay_reservations SET metadata_json = '{}' WHERE id = ?",
            (row_id,),
        )
        connection.commit()
    finally:
        connection.close()
    assert _audit_db(database_path) == LegacyAuditStatus.UNTRUSTED_FLAGS


@pytest.mark.c01_at04
def test_at04_schema_mismatch_misleading_check_substring(tmp_path) -> None:
    database_path = tmp_path / "mismatch.db"
    run_alembic(database_path, "upgrade", REV_0020)
    connection = sqlite3.connect(database_path)
    try:
        insert_replay_sqlite(connection, metadata='{"d13_synthetic_test_only": true}')
        connection.commit()
    finally:
        connection.close()
    run_alembic(database_path, "upgrade", REV_0021)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE d13_replay_reservations_shadow (
                id TEXT PRIMARY KEY,
                synthetic_test_only INTEGER NOT NULL DEFAULT 0
                    CHECK (synthetic_test_only = 1 OR synthetic_test_only = 0)
            )
            """
        )
        connection.commit()
    finally:
        connection.close()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as conn:
        report = audit_legacy_0021_state(conn)
    assert report.status in {
        LegacyAuditStatus.CLEAN,
        LegacyAuditStatus.SCHEMA_MISMATCH,
    }
    assert report.status != LegacyAuditStatus.UNKNOWN