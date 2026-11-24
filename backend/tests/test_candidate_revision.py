import os
import subprocess
import sys
from pathlib import Path

from app.verification.candidate_revision import (
    is_valid_git_sha,
    read_build_revision,
    resolve_revision_evidence,
)


def test_rejects_malformed_sha() -> None:
    assert not is_valid_git_sha("0" * 39)
    assert not is_valid_git_sha("not-a-sha")
    assert is_valid_git_sha("a" * 40)


def test_build_revision_malformed_file_returns_none(tmp_path: Path) -> None:
    bad = tmp_path / "build-revision"
    bad.write_text("not-valid\n", encoding="utf-8")
    assert read_build_revision(bad) is None


def test_revision_conflict_fails_closed(tmp_path: Path, monkeypatch) -> None:
    backend = Path(__file__).resolve().parents[1]
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
    rev_file = tmp_path / "build-revision"
    rev_file.write_text("b" * 40 + "\n", encoding="utf-8")
    monkeypatch.setenv("EDUVIJNA_BUILD_REVISION_PATH", str(rev_file))
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", git_sha)
    evidence = resolve_revision_evidence(cwd=backend)
    assert evidence.revision_conflict is True
    assert evidence.sha_aligned is False
    assert evidence.observed_source == "conflict"


def test_build_revision_alignment_without_git(monkeypatch, tmp_path: Path) -> None:
    sha = "c" * 40
    rev_file = tmp_path / "build-revision"
    rev_file.write_text(sha + "\n", encoding="utf-8")
    monkeypatch.setenv("EDUVIJNA_BUILD_REVISION_PATH", str(rev_file))
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", sha)
    monkeypatch.setattr(
        "app.verification.candidate_revision.shutil.which",
        lambda _name: None,
    )
    evidence = resolve_revision_evidence()
    assert evidence.sha_aligned is True
    assert evidence.observed_source == "build_revision"


def test_day13_verify_mismatch_returns_json_not_empty(tmp_path: Path, monkeypatch) -> None:
    backend = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["EDUVIJNA_CANDIDATE_SHA"] = "0" * 40
    proc = subprocess.run(
        [sys.executable, "-m", "app.day13_verify", "--json"],
        cwd=backend,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    assert proc.stdout.strip()
    assert '"sha_alignment": false' in proc.stdout.lower()