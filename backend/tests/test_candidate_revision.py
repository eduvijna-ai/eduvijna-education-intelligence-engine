"""Revision evidence gates (INT-R01 to R03); unit tests use injection only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.verification.candidate_revision import (
    IMAGE_BUILD_REVISION_PATH,
    ImageRevisionStatus,
    is_valid_git_sha,
    read_image_build_revision,
    resolve_revision_evidence,
)

_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_C = "c" * 40


def test_rejects_malformed_sha() -> None:
    assert not is_valid_git_sha("0" * 39)
    assert not is_valid_git_sha("not-a-sha")
    assert is_valid_git_sha(_SHA_A)


def test_image_revision_absent(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    read = read_image_build_revision(missing)
    assert read.status == ImageRevisionStatus.ABSENT


def test_image_revision_malformed_present(tmp_path: Path) -> None:
    bad = tmp_path / "build-revision"
    bad.write_text("not-valid\n", encoding="utf-8")
    read = read_image_build_revision(bad)
    assert read.status == ImageRevisionStatus.INVALID
    assert read.detail == "image_revision_malformed"


def test_image_revision_non_utf8_fails_even_with_valid_git(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "build-revision"
    bad.write_bytes(b"\xff\xfe")
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", _SHA_A)
    evidence = resolve_revision_evidence(
        git_sha_override=_SHA_A,
        image_revision_path=bad,
    )
    assert evidence.sha_aligned is False
    assert evidence.observed_source == "invalid_image_metadata"
    assert evidence.evidence_error == "image_revision_non_utf8"


def test_revision_conflict_without_git_cli(tmp_path: Path, monkeypatch) -> None:
    rev_file = tmp_path / "build-revision"
    rev_file.write_text(_SHA_B + "\n", encoding="utf-8")
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", _SHA_A)
    evidence = resolve_revision_evidence(
        git_sha_override=_SHA_A,
        image_revision_path=rev_file,
    )
    assert evidence.revision_conflict is True
    assert evidence.sha_aligned is False
    assert evidence.observed_source == "conflict"


def test_build_revision_alignment_without_git(tmp_path: Path, monkeypatch) -> None:
    rev_file = tmp_path / "build-revision"
    rev_file.write_text(_SHA_C + "\n", encoding="utf-8")
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", _SHA_C)
    evidence = resolve_revision_evidence(
        git_sha_override=False,
        image_revision_path=rev_file,
    )
    assert evidence.sha_aligned is True
    assert evidence.observed_source == "build_revision"
    assert evidence.observed_sha == _SHA_C


def test_no_observed_evidence_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    evidence = resolve_revision_evidence(
        git_sha_override=False,
        image_revision_path=missing,
        explicit_candidate=_SHA_A,
    )
    assert evidence.sha_aligned is False
    assert evidence.observed_source == "no_observed_evidence"


def test_malformed_candidate_sha(monkeypatch, tmp_path: Path) -> None:
    rev_file = tmp_path / "build-revision"
    rev_file.write_text(_SHA_C + "\n", encoding="utf-8")
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", "not-a-sha")
    evidence = resolve_revision_evidence(image_revision_path=rev_file)
    assert evidence.candidate_sha_valid is False
    assert evidence.sha_aligned is False
    assert evidence.evidence_error == "CANDIDATE_SHA_MALFORMED"


def test_host_git_valid_image_metadata_absent_ok(tmp_path: Path, monkeypatch) -> None:
    backend = Path(__file__).resolve().parents[1]
    try:
        git_head = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend).decode().strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("git unavailable on host")
    if not is_valid_git_sha(git_head):
        pytest.skip("unexpected git head format")
    missing = tmp_path / "absent"
    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", git_head)
    evidence = resolve_revision_evidence(cwd=backend, image_revision_path=missing)
    assert evidence.sha_aligned is True
    assert evidence.observed_source == "git"


def test_day13_verify_mismatch_returns_structured_json(monkeypatch) -> None:
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
    report = json.loads(proc.stdout)
    assert report["ok"] is False
    assert report["sha_alignment"] is False
    assert "revision_evidence_error" in report or report.get("failure_reason")


def test_resolve_unknown_evidence_unit(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    evidence = resolve_revision_evidence(
        git_sha_override=False,
        image_revision_path=missing,
        explicit_candidate=_SHA_A,
    )
    assert evidence.sha_aligned is False
    assert evidence.observed_source == "no_observed_evidence"


def test_protected_image_revision_not_tamperable_by_runtime_user() -> None:
    """Runs in Compose (non-root); proves root-owned metadata cannot be forged."""
    path = IMAGE_BUILD_REVISION_PATH
    if not path.is_file():
        pytest.skip("image build revision only baked in container images")
    assert os.getuid() != 0
    parent = path.parent
    assert parent.is_dir()
    with pytest.raises(PermissionError):
        path.open("a").close()
    with pytest.raises((PermissionError, OSError)):
        path.chmod(0o666)
    with pytest.raises((PermissionError, OSError)):
        path.unlink()
    with pytest.raises((PermissionError, OSError)):
        (parent / "forged-revision").write_text(_SHA_B, encoding="utf-8")