from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(backend_root() / "alembic.ini"))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def repository_alembic_heads() -> tuple[str, ...]:
    script = ScriptDirectory.from_config(alembic_config())
    heads = tuple(script.get_heads())
    if len(heads) != 1:
        raise AssertionError(f"expected a single Alembic head, found: {heads}")
    return heads


def repository_alembic_head() -> str:
    return repository_alembic_heads()[0]


def read_alembic_version(database_path: Path) -> str:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert row is not None
        return str(row[0])
    finally:
        connection.close()


def run_alembic(
    database_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    return subprocess.run(
        ["alembic", "-c", str(backend_root() / "alembic.ini"), *args],
        cwd=backend_root(),
        env=environment,
        check=check,
        capture_output=True,
        text=True,
    )
