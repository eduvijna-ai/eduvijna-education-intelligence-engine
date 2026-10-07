"""Locate monorepo paths in local dev, GitHub Actions, and Compose backend images."""

from __future__ import annotations

from pathlib import Path


class RepositoryRootError(RuntimeError):
    pass


def repository_root(*, start: Path | None = None) -> Path:
    """Return the Eduvijna repository root directory.

    Resolution order (first match wins while walking parents from each anchor):
    - ``.github/workflows/ci.yml`` (full checkout)
    - ``content/curricula/day5_scope.json`` (curriculum bundle present)
    - Compose split layout: ``/app`` when tests live under ``/app/tests`` and
      ``/content/curricula/day5_scope.json`` exists (legacy image layout)
    """
    anchors = [start.resolve()] if start is not None else [Path(__file__).resolve()]

    seen: set[Path] = set()
    for anchor in anchors:
        for path in (anchor, *anchor.parents):
            if path in seen:
                continue
            seen.add(path)
            if (path / ".github" / "workflows" / "ci.yml").is_file():
                return path
            if (path / "content" / "curricula" / "day5_scope.json").is_file():
                return path

    if Path("/content/curricula/day5_scope.json").is_file() and Path("/app/tests").is_dir():
        return Path("/app")

    raise RepositoryRootError(
        "Could not locate repository root (.github/workflows/ci.yml or content/curricula)"
    )


def curricula_content_dir(*, start: Path | None = None) -> Path:
    root = repository_root(start=start)
    bundled = root / "content" / "curricula"
    if bundled.is_dir():
        return bundled
    legacy = Path("/content/curricula")
    if legacy.is_dir():
        return legacy
    raise RepositoryRootError("Curriculum content directory is missing")


def ci_workflow_file(*, start: Path | None = None) -> Path:
    root = repository_root(start=start)
    workflow = root / ".github" / "workflows" / "ci.yml"
    if workflow.is_file():
        return workflow
    raise RepositoryRootError("CI workflow file is missing from this runtime layout")
