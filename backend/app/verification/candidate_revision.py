"""Exact-candidate vs observed revision evidence (host Git and/or image build metadata)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def is_valid_git_sha(value: str) -> bool:
    return bool(value and _SHA40.match(value.strip().lower()))


def normalize_git_sha(value: str) -> str:
    return value.strip().lower()


def build_revision_path() -> Path:
    explicit = os.environ.get("EDUVIJNA_BUILD_REVISION_PATH", "").strip()
    if explicit:
        return Path(explicit)
    state_path = os.environ.get("EDUVIJNA_EXECUTION_STATE_PATH", "").strip()
    if state_path:
        return Path(state_path).resolve().parent / "build-revision"
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / ".eduvijna" / "build-revision"


def read_build_revision(path: Path | None = None) -> str | None:
    target = path or build_revision_path()
    if not target.is_file():
        return None
    text = target.read_text(encoding="utf-8").strip()
    if not is_valid_git_sha(text):
        return None
    return normalize_git_sha(text)


def git_head(cwd: Path | None = None) -> str | None:
    if shutil.which("git") is None:
        return None
    workdir = cwd or Path(__file__).resolve().parents[2]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=workdir,
            stderr=subprocess.DEVNULL,
        ).decode()
    except (subprocess.CalledProcessError, OSError):
        return None
    text = out.strip()
    if not is_valid_git_sha(text):
        return None
    return normalize_git_sha(text)


@dataclass(frozen=True, slots=True)
class RevisionEvidence:
    candidate_sha: str
    git_sha: str | None
    build_revision_sha: str | None
    observed_sha: str
    observed_source: str
    revision_conflict: bool
    sha_aligned: bool
    candidate_sha_valid: bool

    def as_report_fields(self) -> dict[str, object]:
        return {
            "candidate_sha": self.candidate_sha,
            "head_sha": self.observed_sha,
            "git_head_sha": self.git_sha or "unknown",
            "build_revision_sha": self.build_revision_sha or "unknown",
            "observed_revision_source": self.observed_source,
            "revision_conflict": self.revision_conflict,
            "sha_alignment": self.sha_aligned,
            "candidate_sha_valid": self.candidate_sha_valid,
        }


def resolve_candidate_sha(explicit_env: str | None = None) -> str:
    if explicit_env is not None:
        explicit = explicit_env.strip()
    else:
        explicit = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip()
    if explicit:
        return normalize_git_sha(explicit) if is_valid_git_sha(explicit) else explicit.strip()
    observed = git_head()
    return observed or "unknown"


def resolve_revision_evidence(
    *,
    cwd: Path | None = None,
    explicit_candidate: str | None = None,
) -> RevisionEvidence:
    candidate = resolve_candidate_sha(explicit_candidate)
    candidate_valid = is_valid_git_sha(candidate)
    git_sha = git_head(cwd)
    build_sha = read_build_revision()

    revision_conflict = bool(
        git_sha is not None and build_sha is not None and git_sha != build_sha
    )

    if revision_conflict:
        observed = "unknown"
        source = "conflict"
        aligned = False
    elif git_sha is not None:
        observed = git_sha
        source = "git"
        aligned = candidate_valid and candidate == git_sha
    elif build_sha is not None:
        observed = build_sha
        source = "build_revision"
        aligned = candidate_valid and candidate == build_sha
    else:
        observed = "unknown"
        source = "unknown"
        aligned = False

    if not candidate_valid:
        aligned = False

    return RevisionEvidence(
        candidate_sha=candidate,
        git_sha=git_sha,
        build_revision_sha=build_sha,
        observed_sha=observed,
        observed_source=source,
        revision_conflict=revision_conflict,
        sha_aligned=aligned,
        candidate_sha_valid=candidate_valid,
    )