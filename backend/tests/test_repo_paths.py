from __future__ import annotations

from pathlib import Path

import pytest

from app.repo_paths import (
    RepositoryRootError,
    ci_workflow_file,
    curricula_content_dir,
    repository_root,
)


def test_repository_root_from_backend_test_file() -> None:
    start = Path(__file__).resolve()
    root = repository_root(start=start)
    assert (root / "content" / "curricula" / "day5_scope.json").is_file()
    assert (root / ".github" / "workflows" / "ci.yml").is_file()


def test_repository_root_compose_like_layout(tmp_path: Path) -> None:
    tests_dir = tmp_path / "app" / "tests"
    tests_dir.mkdir(parents=True)
    curricula = tmp_path / "content" / "curricula"
    curricula.mkdir(parents=True)
    (curricula / "day5_scope.json").write_text("{}", encoding="utf-8")
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    fake_test = tests_dir / "test_example.py"
    fake_test.write_text("#", encoding="utf-8")
    assert repository_root(start=fake_test) == tmp_path
    assert ci_workflow_file(start=fake_test) == workflow_dir / "ci.yml"
    assert curricula_content_dir(start=fake_test) == curricula


def test_repository_root_missing_raises(tmp_path: Path) -> None:
    lone = tmp_path / "orphan.py"
    lone.write_text("#", encoding="utf-8")
    with pytest.raises(RepositoryRootError):
        repository_root(start=lone)
