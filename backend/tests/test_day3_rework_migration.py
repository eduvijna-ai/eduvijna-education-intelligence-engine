from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from uuid import uuid4


def _run_alembic(
    database_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    return subprocess.run(
        ["alembic", "-c", str(backend_root / "alembic.ini"), *args],
        cwd=backend_root,
        env=environment,
        check=check,
        capture_output=True,
        text=True,
    )


def _revision(database_path: Path) -> str:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert row is not None
        return str(row[0])
    finally:
        connection.close()


def _table_names(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()


def test_partial_day3_schema_failure_rolls_back_and_can_retry(tmp_path: Path) -> None:
    database_path = tmp_path / "partial-day3.db"
    _run_alembic(database_path, "upgrade", "20261002_0004")

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE source_diffs (id TEXT PRIMARY KEY)"
        )
        connection.commit()
    finally:
        connection.close()

    result = _run_alembic(database_path, "upgrade", "head", check=False)
    assert result.returncode != 0
    assert _revision(database_path) == "20261002_0004"
    tables = _table_names(database_path)
    assert "source_revisions" not in tables
    assert "source_audit_events" not in tables
    assert "source_diffs" in tables

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DROP TABLE source_diffs")
        connection.commit()
    finally:
        connection.close()

    _run_alembic(database_path, "upgrade", "head")
    assert _revision(database_path) == "20261004_0009"


def test_foreign_key_validation_failure_keeps_old_revision_and_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "fk-failure.db"
    _run_alembic(database_path, "upgrade", "20261002_0004")

    orphan_question = str(uuid4())
    orphan_source = str(uuid4())
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO question_sources (question_id, source_id) VALUES (?, ?)",
            (orphan_question, orphan_source),
        )
        connection.commit()
    finally:
        connection.close()

    result = _run_alembic(database_path, "upgrade", "head", check=False)
    assert result.returncode != 0
    assert _revision(database_path) == "20261002_0004"
    tables = _table_names(database_path)
    assert "source_revisions" not in tables
    assert "source_diffs" not in tables

    connection = sqlite3.connect(database_path)
    try:
        orphan = connection.execute(
            "SELECT question_id, source_id FROM question_sources"
        ).fetchone()
        assert orphan == (orphan_question, orphan_source)
        connection.execute("DELETE FROM question_sources")
        connection.commit()
    finally:
        connection.close()

    _run_alembic(database_path, "upgrade", "head")
    assert _revision(database_path) == "20261004_0009"

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
