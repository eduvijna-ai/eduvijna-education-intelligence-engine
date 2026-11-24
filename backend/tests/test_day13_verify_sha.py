import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.verification.candidate_revision import resolve_revision_evidence


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


def test_day13_verify_passes_with_aligned_sha() -> None:
    backend = Path(__file__).resolve().parents[1]
    evidence = resolve_revision_evidence(cwd=backend)
    if not evidence.sha_aligned and evidence.observed_source == "unknown":
        proc = subprocess.run(
            [sys.executable, "-m", "app.day13_verify", "--json"],
            cwd=backend,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        assert proc.returncode != 0
        assert proc.stdout.strip()
        report = json.loads(proc.stdout)
        assert report["sha_alignment"] is False
        return

    candidate = evidence.observed_sha if evidence.observed_source != "unknown" else ""
    if shutil.which("git"):
        git_head = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
        )
        candidate = git_head

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