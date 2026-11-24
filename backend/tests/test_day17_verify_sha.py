import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.verification.candidate_revision import (
    IMAGE_BUILD_REVISION_PATH,
    ImageRevisionStatus,
    is_valid_git_sha,
    read_image_build_revision,
)


def test_day17_verify_fails_on_sha_mismatch() -> None:
    env = os.environ.copy()
    env["EDUVIJNA_CANDIDATE_SHA"] = "0" * 40
    proc = subprocess.run(
        [sys.executable, "-m", "app.day17_verify", "--json"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["ok"] is False


def _aligned_candidate_for_environment(backend: Path) -> str:
    if shutil.which("git"):
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
    image = read_image_build_revision(IMAGE_BUILD_REVISION_PATH)
    assert image.status == ImageRevisionStatus.VALID and image.sha is not None
    expected = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip().lower()
    assert expected == image.sha
    return expected


def test_day17_verify_passes_with_aligned_sha() -> None:
    backend = Path(__file__).resolve().parents[1]
    candidate = _aligned_candidate_for_environment(backend)
    assert is_valid_git_sha(candidate)
    env = os.environ.copy()
    env["EDUVIJNA_CANDIDATE_SHA"] = candidate
    proc = subprocess.run(
        [sys.executable, "-m", "app.day17_verify", "--json"],
        cwd=backend,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["scope_counts"]["TOTAL"] == 36
