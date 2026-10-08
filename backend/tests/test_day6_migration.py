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


def test_day6_migration_upgrade_downgrade_reupgrade(tmp_path: Path) -> None:
    database = tmp_path / "day6-migration.db"
    _run_alembic(database, "upgrade", "head")
    tables = _table_names(database)
    assert "ei_taxonomy_registry" in tables
    assert "ei_validation_audit_runs" in tables
    _run_alembic(database, "downgrade", "20261004_0009")
    assert "ei_taxonomy_registry" not in _table_names(database)
    _run_alembic(database, "upgrade", "head")
    assert "ei_taxonomy_registry" in _table_names(database)
    check = _run_alembic(database, "check")
    assert check.returncode == 0
