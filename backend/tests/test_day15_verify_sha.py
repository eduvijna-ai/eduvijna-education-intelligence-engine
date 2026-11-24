import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def test_day15_verify_fails_on_sha_mismatch() -> None:
    env = {**os.environ, "EDUVIJNA_CANDIDATE_SHA": "0" * 40}
    proc = subprocess.run(
        [sys.executable, "-m", "app.day15_verify", "--json"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    report = json.loads(proc.stdout)
    assert report.get("ok") is False
    assert report.get("sha_alignment") is False


@pytest.mark.skipif(
    not (BACKEND.parent / ".git").exists(),
    reason="git required for aligned-sha verifier smoke",
)
def test_day15_verify_passes_with_aligned_sha() -> None:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=BACKEND.parent,
        text=True,
    ).strip()
    env = {**os.environ, "EDUVIJNA_CANDIDATE_SHA": head}
    proc = subprocess.run(
        [sys.executable, "-m", "app.day15_verify", "--json"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report.get("ok") is True
    assert report.get("sha_alignment") is True