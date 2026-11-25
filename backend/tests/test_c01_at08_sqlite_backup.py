"""AT08 — populated SQLite backup API restore integrity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.c01_at_support import (
    REV_0021,
    replay_rows_digest,
    run_alembic,
    seed_minimal_nonempty_canonical,
    sqlite_schema_digest,
    sqlite_table_count,
    sqlite_table_row_digest,
)


@pytest.mark.c01_at08
def test_at08_populated_sqlite_backup_restore_fingerprints_match(tmp_path: Path) -> None:
    database_path = tmp_path / "backup-src.db"
    restored_path = tmp_path / "backup-dst.db"
    run_alembic(database_path, "upgrade", REV_0021)
    connection = sqlite3.connect(database_path)
    try:
        counts = seed_minimal_nonempty_canonical(connection)
        assert counts["organizations"] > 0
        assert counts["d13_replay_reservations"] > 0
        before_rows = replay_rows_digest(connection)
        before_schema = sqlite_schema_digest(connection)
        table_digests = {
            table: sqlite_table_row_digest(connection, table)
            for table in (
                "organizations",
                "institutions",
                "sources",
                "source_revisions",
                "d13_replay_reservations",
            )
        }
        backup = sqlite3.connect(str(restored_path))
        connection.backup(backup)
        backup.close()
    finally:
        connection.close()

    restored = sqlite3.connect(restored_path)
    try:
        assert restored.execute("SELECT version_num FROM alembic_version").fetchone()[0] == REV_0021
        assert sqlite_table_count(restored, "organizations") == counts["organizations"]
        replay_expected = counts["d13_replay_reservations"]
        assert sqlite_table_count(restored, "d13_replay_reservations") == replay_expected
        assert replay_rows_digest(restored) == before_rows
        assert sqlite_schema_digest(restored) == before_schema
        for table, digest in table_digests.items():
            assert sqlite_table_row_digest(restored, table) == digest
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        restored.close()