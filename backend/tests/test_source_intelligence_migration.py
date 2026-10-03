from __future__ import annotations

import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import SourceAuditEvent, SourceDiff, SourceRevision


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


def _seed_day2_records(database_path: Path) -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    ids = {
        "setting": str(uuid4()),
        "source": str(uuid4()),
        "question": str(uuid4()),
    }
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute(
            """
            INSERT INTO system_settings (id, key, value, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (ids["setting"], "day3.migration.seed", "preserve", now),
        )
        connection.execute(
            """
            INSERT INTO sources (
                id, source_type, title, authority, country, board_or_exam,
                academic_year, effective_date, retrieved_at, checksum,
                copyright_classification, trust_tier, anythingllm_workspace,
                status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["source"],
                "official_syllabus",
                "Existing Day 2 source",
                "Synthetic Authority",
                "IN",
                "SYNTH",
                "2026-27",
                None,
                None,
                None,
                "official-public-document",
                "official_primary",
                None,
                "staged",
                "{}",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO questions (
                id, external_code, content_version, origin_type,
                curriculum_version_id, exam_version_id, primary_curriculum_node_id,
                question_type, stem_text, stem_latex, solution_text, solution_latex,
                answer_json, difficulty, cognitive_level, age_min, age_max,
                grade_year_codes, rubric_json, status, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["question"],
                "existing-question",
                1,
                "generated",
                None,
                None,
                None,
                "descriptive",
                "Existing Day 2 question",
                None,
                None,
                None,
                "{}",
                None,
                None,
                None,
                None,
                "[]",
                "{}",
                "draft",
                "{}",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return ids


def _assert_day2_records(database_path: Path, ids: dict[str, str]) -> None:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        assert connection.execute(
            "SELECT value FROM system_settings WHERE id = ?",
            (ids["setting"],),
        ).fetchone() == ("preserve",)
        assert connection.execute(
            "SELECT title FROM sources WHERE id = ?",
            (ids["source"],),
        ).fetchone() == ("Existing Day 2 source",)
        assert connection.execute(
            "SELECT stem_text FROM questions WHERE id = ?",
            (ids["question"],),
        ).fetchone() == ("Existing Day 2 question",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_day3_migration_preserves_day1_day2_records(tmp_path: Path) -> None:
    database_path = tmp_path / "day3-migration.db"

    _run_alembic(database_path, "upgrade", "20261002_0004")
    ids = _seed_day2_records(database_path)

    _run_alembic(database_path, "upgrade", "head")
    _assert_day2_records(database_path, ids)

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "source_revisions",
            "source_diffs",
            "source_audit_events",
            "curriculum_version_source_revisions",
            "exam_version_source_revisions",
            "question_source_revisions",
            "policy_rule_source_revisions",
        }.issubset(tables)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261003_0007",
        )
    finally:
        connection.close()

    _run_alembic(database_path, "downgrade", "20261002_0004")
    _assert_day2_records(database_path, ids)

    _run_alembic(database_path, "upgrade", "head")
    _assert_day2_records(database_path, ids)


def test_failed_day3_upgrade_keeps_previous_revision(tmp_path: Path) -> None:
    database_path = tmp_path / "day3-failed-migration.db"
    _run_alembic(database_path, "upgrade", "20261002_0004")

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE source_revisions (id TEXT PRIMARY KEY)")
        connection.commit()
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261002_0004",
        )
    finally:
        connection.close()

    result = _run_alembic(database_path, "upgrade", "head", check=False)
    assert result.returncode != 0

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261002_0004",
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    "table",
    [
        SourceRevision.__table__,
        SourceDiff.__table__,
        SourceAuditEvent.__table__,
    ],
)
def test_source_intelligence_tables_compile_for_postgresql(table: object) -> None:
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE" in sql
