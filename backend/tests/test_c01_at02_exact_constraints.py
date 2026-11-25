"""AT02 — dialect-exact synthetic marker and source_revisions lifecycle constraints."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.models import day13_replay  # noqa: F401
from tests.c01_at_support import (
    REV_0006,
    REV_0020,
    REV_0021,
    insert_active_source_revision_sqlite,
    insert_minimal_source_sqlite,
    insert_replay_sqlite,
    run_alembic,
)
from tests.c01_disposable_pg import C01_PG_OPT_IN, validated_disposable_pg_url
from tests.migration_test_support import run_alembic as migration_run


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.mark.c01_at02
def test_at02_sqlite_migrated_table_rejects_invalid_synthetic_values(tmp_path) -> None:
    database_path = tmp_path / "at02-sqlite.db"
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
        row_id = connection.execute(
            "SELECT id FROM d13_replay_reservations LIMIT 1"
        ).fetchone()
        if row_id is None:
            meta = '{"d13_synthetic_test_only": true}'
            row_id = (insert_replay_sqlite(connection, metadata=meta),)
            connection.commit()
        row_id = row_id[0]
        for bad in (0, 2, -1):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                connection.execute(
                    "UPDATE d13_replay_reservations SET synthetic_test_only = ? WHERE id = ?",
                    (bad, row_id),
                )
                connection.commit()
            connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE d13_replay_reservations SET synthetic_test_only = ? WHERE id = ?",
                ("1junk", row_id),
            )
            connection.commit()
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE d13_replay_reservations SET synthetic_test_only = NULL WHERE id = ?",
                (row_id,),
            )
            connection.commit()
    finally:
        connection.close()


@pytest.mark.c01_at02
def test_at02_orm_create_all_synthetic_check_labeled_separate_from_migration(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'orm-only.db'}")
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        ddl = conn.execute(
            text(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='d13_replay_reservations'"
            )
        ).scalar_one()
        assert "synthetic_test_only = 1" in ddl


@pytest.mark.c01_at02
def test_at02_source_revisions_active_slot_lifecycle_sqlite(tmp_path) -> None:
    database_path = tmp_path / "slot.db"
    migration_run(database_path, "upgrade", REV_0006)
    connection = sqlite3.connect(database_path)
    try:
        source_id = insert_minimal_source_sqlite(connection, title="AT02")
        insert_active_source_revision_sqlite(connection, source_id=source_id, revision_number=1)
        connection.commit()
        for status, slot in (("active", None), ("active", 0), ("active", 2), ("retired", 1)):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                ts = _now()
                connection.execute(
                    """
                    INSERT INTO source_revisions (
                        id, source_id, revision_number, ingestion_method, checksum,
                        source_snapshot_checksum, content_type, byte_size, retrieved_at,
                        extraction_status, extraction_metadata_json, status, active_slot,
                        metadata_json, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(uuid.uuid4()),
                        source_id,
                        2,
                        "manual",
                        "b" * 64,
                        "c" * 64,
                        "application/pdf",
                        1,
                        ts,
                        "validated",
                        "{}",
                        status,
                        slot,
                        "{}",
                        ts,
                        ts,
                    ),
                )
                connection.commit()
            connection.rollback()
        ts = _now()
        connection.execute(
            """
            INSERT INTO source_revisions (
                id, source_id, revision_number, ingestion_method, checksum,
                source_snapshot_checksum, content_type, byte_size, retrieved_at,
                extraction_status, extraction_metadata_json, status, active_slot,
                metadata_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                source_id,
                3,
                "manual",
                "c" * 64,
                "d" * 64,
                "application/pdf",
                1,
                ts,
                "validated",
                "{}",
                "retired",
                None,
                "{}",
                ts,
                ts,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
            insert_active_source_revision_sqlite(
                connection, source_id=source_id, revision_number=4
            )
            connection.commit()
        connection.rollback()
        other_source = insert_minimal_source_sqlite(connection, title="AT02-b")
        insert_active_source_revision_sqlite(connection, source_id=other_source, revision_number=1)
        connection.commit()
    finally:
        connection.close()


@pytest.mark.c01_at02
def test_at02_postgres_compile_uses_is_true_predicate() -> None:
    table = Base.metadata.tables["d13_replay_reservations"]
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "synthetic_test_only IS TRUE" in ddl


@pytest.mark.c01_at02
@pytest.mark.skipif(__import__("os").environ.get(C01_PG_OPT_IN) != "1", reason="PG opt-in")
def test_at02_postgres_rejects_false_and_null_synthetic() -> None:
    url = validated_disposable_pg_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE at02_syn (v boolean)"))
        conn.commit()
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE at02_syn ADD CONSTRAINT ck_at02 CHECK (v IS TRUE)"))
        conn.commit()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO at02_syn (v) VALUES (true)"))
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO at02_syn (v) VALUES (false)"))
        conn.rollback()
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO at02_syn (v) VALUES (NULL)"))