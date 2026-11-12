import os
import subprocess
import sys
from pathlib import Path

import pytest


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
    head = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
    )
    env = {**os.environ, "EDUVIJNA_CANDIDATE_SHA": head}
    proc = subprocess.run(
        [sys.executable, "-m", "app.day12_verify"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if head == "unknown":
        pytest.skip("git head unavailable")
    assert proc.returncode == 0
