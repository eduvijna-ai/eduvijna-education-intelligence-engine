import json
import os
import subprocess
import sys
from pathlib import Path


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
    report = json.loads(proc.stdout)
    assert report["sha_alignment"] is False


def test_day13_verify_passes_with_aligned_sha() -> None:
    backend = Path(__file__).resolve().parents[1]
    head = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
    )
    env = os.environ.copy()
    env["EDUVIJNA_CANDIDATE_SHA"] = head
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
    assert report["synthetic_fixture_pass"] is True