"""AT10 — exact-head evidence metadata and mandatory collection gates."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.c01_at_support import acceptance_git_sha, repository_alembic_head, revision_graph_token

AT_MODULES = (
    "tests/test_c01_at01_disposable_harness.py",
    "tests/test_c01_at02_exact_constraints.py",
    "tests/test_c01_at03_0021_preflight.py",
    "tests/test_c01_at04_legacy_audit.py",
    "tests/test_c01_at05_concurrency.py",
    "tests/test_c01_at06_migration_paths.py",
    "tests/test_c01_at07_atomic_recovery.py",
    "tests/test_c01_at08_sqlite_backup.py",
    "tests/test_c01_at09_pg_backup.py",
    "tests/test_c01_at10_ci_evidence.py",
)


@pytest.mark.c01_at10
def test_at10_git_head_matches_candidate_sha_env_when_set() -> None:
    head = acceptance_git_sha()
    assert len(head) == 40
    env_sha = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip()
    if env_sha:
        assert head == env_sha


@pytest.mark.c01_at10
def test_at10_all_acceptance_modules_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for module in AT_MODULES:
        assert (root / module).is_file(), module


@pytest.mark.c01_at10
def test_at10_pytest_collects_all_at_modules() -> None:
    backend = Path(__file__).resolve().parents[1]
    collect = subprocess.run(
        [sys.executable, "-m", "pytest", *AT_MODULES, "--collect-only", "-q"],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
    )
    assert collect.returncode == 0, collect.stderr
    import re

    per_file = re.findall(r":\s*(\d+)\s*$", collect.stdout, flags=re.MULTILINE)
    total = sum(int(n) for n in per_file)
    if total == 0:
        match = re.search(r"(\d+)\s+tests?\s+collected", collect.stdout)
        assert match is not None, collect.stdout
        total = int(match.group(1))
    assert total >= 20


@pytest.mark.c01_at10
def test_at10_repository_alembic_head_and_revision_graph_recorded() -> None:
    assert repository_alembic_head().startswith("2026")
    assert len(revision_graph_token()) == 64