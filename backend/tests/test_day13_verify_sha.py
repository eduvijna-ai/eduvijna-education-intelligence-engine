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
    resolve_revision_evidence,
)


def test_day13_verify_fails_on_sha_mismatch() -> None:
    env = os.environ.copy()
    env["EDUVIJNA_CANDIDATE_SHA"] = "0" * 40
    proc = subprocess.run(
        [sys.executable, "-m", "app.day13_verify", "--json"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    assert proc.stdout.strip(), proc.stderr
    report = json.loads(proc.stdout)
    assert report["sha_alignment"] is False
    assert report["ok"] is False


def _aligned_candidate_for_environment(backend: Path) -> tuple[str, str]:
    """Return (candidate_sha, evidence_mode) for host Git or container image metadata."""
    if shutil.which("git"):
        git_head = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
        )
        assert is_valid_git_sha(git_head)
        return git_head, "git"
    image = read_image_build_revision(IMAGE_BUILD_REVISION_PATH)
    assert image.status == ImageRevisionStatus.VALID and image.sha is not None
    expected = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip().lower()
    assert is_valid_git_sha(expected), "container requires EDUVIJNA_CANDIDATE_SHA"
    assert expected == image.sha, "expected SHA must match independent image metadata"
    return expected, "build_revision"


def test_day13_verify_passes_with_aligned_sha() -> None:
    backend = Path(__file__).resolve().parents[1]
    candidate, mode = _aligned_candidate_for_environment(backend)

    if mode == "git":
        evidence = resolve_revision_evidence(cwd=backend, explicit_candidate=candidate)
    else:
        evidence = resolve_revision_evidence(
            explicit_candidate=candidate,
            git_sha_override=False,
        )

    assert evidence.sha_aligned is True, evidence.as_report_fields()
    assert evidence.observed_source == mode
    assert evidence.observed_sha == candidate

    env = os.environ.copy()
    env["EDUVIJNA_CANDIDATE_SHA"] = candidate
    proc = subprocess.run(
        [sys.executable, "-m", "app.day13_verify", "--json"],
        cwd=backend,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["sha_alignment"] is True
    assert report["synthetic_fixture_pass"] is True