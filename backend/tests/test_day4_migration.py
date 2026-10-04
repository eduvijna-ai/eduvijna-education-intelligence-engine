from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path


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


def _columns(database_path: Path, table_name: str) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
    finally:
        connection.close()


def test_day4_migration_upgrade_downgrade_reupgrade_preserves_prior_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "day4-migration.db"

    _run_alembic(database, "upgrade", "20261003_0007")
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO education_frameworks
            (id, code, name, country, active, created_at, updated_at)
            VALUES
            ('framework-before-d4', 'pre-d4', 'Pre Day 4', 'India', 1,
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        connection.commit()
    finally:
        connection.close()

    _run_alembic(database, "upgrade", "20261004_0008")
    assert "curriculum_alignments" in _table_names(database)
    assert "assessment_evidence" in _table_names(database)
    expected_columns = {
        "authority",
        "version_code",
        "source_revision_id",
        "source_locator",
    }
    assert expected_columns <= _columns(database, "education_frameworks")

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM education_frameworks WHERE id='framework-before-d4'"
        ).fetchone() == (1,)
    finally:
        connection.close()

    _run_alembic(database, "downgrade", "20261003_0007")
    assert "curriculum_alignments" not in _table_names(database)
    assert "assessment_evidence" not in _table_names(database)
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM education_frameworks WHERE id='framework-before-d4'"
        ).fetchone() == (1,)
    finally:
        connection.close()

    _run_alembic(database, "upgrade", "head")
    assert "curriculum_alignments" in _table_names(database)
    assert "assessment_evidence" in _table_names(database)


def test_day4_failure_rolls_back_partial_schema_and_retries(tmp_path: Path) -> None:
    database = tmp_path / "day4-failed-upgrade.db"
    _run_alembic(database, "upgrade", "20261003_0007")
    connection = sqlite3.connect(database)
    try:
        # Simulate a partial/manual schema collision after several earlier D4
        # alterations would otherwise have succeeded.
        connection.execute("CREATE TABLE curriculum_alignments (sentinel TEXT)")
        connection.execute("INSERT INTO curriculum_alignments VALUES ('retain')")
        connection.commit()
    finally:
        connection.close()
    result = _run_alembic(database, "upgrade", "head", check=False)
    assert result.returncode != 0
    assert "source_revision_id" not in _columns(database, "education_frameworks")
    assert "authority" not in _columns(database, "education_frameworks")
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261003_0007",
        )
        assert connection.execute("SELECT * FROM curriculum_alignments").fetchall() == [("retain",)]
        connection.execute("DROP TABLE curriculum_alignments")
        connection.commit()
    finally:
        connection.close()
    _run_alembic(database, "upgrade", "head")
    _run_alembic(database, "check")
    assert "source_revision_id" in _columns(database, "education_frameworks")
