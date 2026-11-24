"""Exact-candidate vs observed revision evidence (host Git and/or image build metadata)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

_SHA40 = re.compile(r"^[0-9a-f]{40}$")

# Root-owned, image-baked metadata outside writable /app (see backend/Dockerfile).
IMAGE_BUILD_REVISION_PATH = Path("/etc/eduvijna/build-revision")

type GitOverride = str | Literal[False] | None

ObservedSource = Literal[
    "git",
    "build_revision",
    "conflict",
    "unknown",
    "invalid_image_metadata",
    "no_observed_evidence",
]


class ImageRevisionStatus(StrEnum):
    ABSENT = "absent"
    VALID = "valid"
    INVALID = "invalid"
    UNREADABLE = "unreadable"


def is_valid_git_sha(value: str) -> bool:
    return bool(value and _SHA40.match(value.strip().lower()))


def normalize_git_sha(value: str) -> str:
    return value.strip().lower()


@dataclass(frozen=True, slots=True)
class ImageRevisionRead:
    status: ImageRevisionStatus
    sha: str | None = None
    detail: str | None = None


def read_image_build_revision(path: Path = IMAGE_BUILD_REVISION_PATH) -> ImageRevisionRead:
    """Read fixed image metadata path only — no runtime env overrides."""
    if not path.exists():
        return ImageRevisionRead(status=ImageRevisionStatus.ABSENT)
    if not path.is_file():
        return ImageRevisionRead(
            status=ImageRevisionStatus.INVALID,
            detail="image_revision_not_a_file",
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return ImageRevisionRead(
            status=ImageRevisionStatus.UNREADABLE,
            detail=f"image_revision_os_error:{exc.__class__.__name__}",
        )
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return ImageRevisionRead(
            status=ImageRevisionStatus.UNREADABLE,
            detail="image_revision_non_utf8",
        )
    if not text:
        return ImageRevisionRead(status=ImageRevisionStatus.INVALID, detail="image_revision_empty")
    if not is_valid_git_sha(text):
        return ImageRevisionRead(
            status=ImageRevisionStatus.INVALID,
            detail="image_revision_malformed",
        )
    return ImageRevisionRead(status=ImageRevisionStatus.VALID, sha=normalize_git_sha(text))


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
    image_revision_status: str
    observed_sha: str
    observed_source: ObservedSource
    revision_conflict: bool
    sha_aligned: bool
    candidate_sha_valid: bool
    evidence_error: str | None

    def as_report_fields(self) -> dict[str, object]:
        return {
            "candidate_sha": self.candidate_sha,
            "head_sha": self.observed_sha,
            "git_head_sha": self.git_sha or "unknown",
            "build_revision_sha": self.build_revision_sha or "unknown",
            "image_revision_status": self.image_revision_status,
            "observed_revision_source": self.observed_source,
            "revision_conflict": self.revision_conflict,
            "sha_alignment": self.sha_aligned,
            "candidate_sha_valid": self.candidate_sha_valid,
            "revision_evidence_error": self.evidence_error,
        }


def resolve_candidate_sha(explicit_env: str | None = None) -> tuple[str, bool, str | None]:
    if explicit_env is not None:
        explicit = explicit_env.strip()
    else:
        explicit = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip()
    if explicit:
        if is_valid_git_sha(explicit):
            return normalize_git_sha(explicit), True, None
        return explicit, False, "CANDIDATE_SHA_MALFORMED"
    observed = git_head()
    if observed:
        return observed, True, None
    return "unknown", False, "CANDIDATE_SHA_ABSENT"


def resolve_revision_evidence(
    *,
    cwd: Path | None = None,
    explicit_candidate: str | None = None,
    git_sha_override: GitOverride = None,
    image_revision_path: Path | None = None,
) -> RevisionEvidence:
    """Resolve SHA alignment. Optional overrides are for unit tests only."""
    candidate, candidate_valid, candidate_err = resolve_candidate_sha(explicit_candidate)
    if git_sha_override is False:
        git_sha = None
    elif isinstance(git_sha_override, str):
        if is_valid_git_sha(git_sha_override):
            git_sha = normalize_git_sha(git_sha_override)
        else:
            git_sha = None
    else:
        git_sha = git_head(cwd)

    image_path = (
        image_revision_path if image_revision_path is not None else IMAGE_BUILD_REVISION_PATH
    )
    image_read = read_image_build_revision(image_path)
    build_sha = image_read.sha if image_read.status == ImageRevisionStatus.VALID else None

    evidence_error = candidate_err
    revision_conflict = False
    observed_source: ObservedSource = "unknown"
    observed = "unknown"
    aligned = False

    if image_read.status in (ImageRevisionStatus.INVALID, ImageRevisionStatus.UNREADABLE):
        evidence_error = evidence_error or image_read.detail or "IMAGE_REVISION_INVALID"
        observed_source = "invalid_image_metadata"
        aligned = False
    elif git_sha is not None and build_sha is not None and git_sha != build_sha:
        revision_conflict = True
        evidence_error = evidence_error or "GIT_IMAGE_REVISION_CONFLICT"
        observed_source = "conflict"
        aligned = False
    elif git_sha is not None:
        observed = git_sha
        observed_source = "git"
        aligned = candidate_valid and candidate == git_sha and evidence_error is None
    elif build_sha is not None:
        observed = build_sha
        observed_source = "build_revision"
        aligned = candidate_valid and candidate == build_sha and evidence_error is None
    else:
        observed_source = "no_observed_evidence"
        evidence_error = evidence_error or "NO_OBSERVED_REVISION_EVIDENCE"
        aligned = False

    if not candidate_valid:
        aligned = False

    return RevisionEvidence(
        candidate_sha=candidate,
        git_sha=git_sha,
        build_revision_sha=build_sha,
        image_revision_status=image_read.status.value,
        observed_sha=observed,
        observed_source=observed_source,
        revision_conflict=revision_conflict,
        sha_aligned=aligned,
        candidate_sha_valid=candidate_valid,
        evidence_error=evidence_error,
    )