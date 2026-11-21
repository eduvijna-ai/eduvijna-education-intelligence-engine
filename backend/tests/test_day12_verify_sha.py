import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_day12_verify_fails_on_sha_mismatch() -> None:
    backend = Path(__file__).resolve().parents[1]
    env = {**os.environ, "EDUVIJNA_CANDIDATE_SHA": "0" * 40}
    proc = subprocess.run(
        [sys.executable, "-m", "app.day12_verify"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0


def test_day12_verify_passes_with_aligned_sha() -> None:
    backend = Path(__file__).resolve().parents[1]
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
    ) if shutil.which("git") else None
    head = (
        git_head.stdout.strip()
        if git_head is not None and git_head.returncode == 0
        else "unknown"
    )
    env = {
        **os.environ,
        "EDUVIJNA_CANDIDATE_SHA": (
            head if head != "unknown" else os.environ.get("EDUVIJNA_CANDIDATE_SHA", "0" * 40)
        ),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "app.day12_verify", "--json"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if head == "unknown":
        # An image with no Git checkout must fail closed, not fake SHA proof or skip.
        assert proc.returncode != 0
        assert '"sha_alignment": false' in proc.stdout
    else:
        assert proc.returncode == 0
        assert '"sha_alignment": true' in proc.stdout
