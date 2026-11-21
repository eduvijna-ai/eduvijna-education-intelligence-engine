"""Offline tests for private official source intake CLI (CORE35-INTAKE)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from app.jee_advanced.constants import OFFICIAL_DISCOVERY_URLS
from app.jee_advanced.official_source_intake import (
    MANIFEST_KIND,
    build_intake_slots,
    build_manifest,
    check_url,
    download_one,
    inspect_pdf,
    main,
    run_intake,
    validate_private_output_dir,
)


def _minimal_pdf(extra: bytes = b"") -> bytes:
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<<>>endobj\n"
        b"trailer<<>>\n"
        b"%%EOF\n"
        + extra
    )
    assert len(body) >= 30
    return body


class _ByteResponse:
    def __init__(self, data: bytes, url: str, content_type: str = "application/pdf") -> None:
        self._data = data
        self._url = url
        self.headers = {"Content-Type": content_type}

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            out, self._data = self._data, b""
            return out
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk

    def __enter__(self) -> _ByteResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _MockOpener:
    def __init__(self, mapping: dict[str, bytes]) -> None:
        self.mapping = mapping

    def open(self, request: urllib.request.Request, timeout: int = 25) -> _ByteResponse:
        url = request.full_url
        if url not in self.mapping:
            raise urllib.error.URLError(f"no mock for {url}")
        return _ByteResponse(self.mapping[url], url)


def test_list_only_prints_six_slots_without_files(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--list-only"])
    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 6
    slot_ids = {line.split("\t", 1)[0] for line in out}
    assert slot_ids == {slot.slot_id for slot in build_intake_slots()}
    urls = set(OFFICIAL_DISCOVERY_URLS.values())
    for slot in build_intake_slots():
        assert slot.candidate_url.startswith("https://jeeadv.ac.in/")
        assert slot.candidate_url in urls
    # No files created in cwd
    assert not list(Path.cwd().glob("eduvijna-d12-2026-intake-UNAPPROVED.json"))


def test_build_intake_slots_match_registry() -> None:
    slots = build_intake_slots()
    assert len(slots) == 6
    assert slots[0].slot_id == "jee_advanced.2026.brochure"


def test_check_url_rejects_bad_hosts_and_schemes() -> None:
    with pytest.raises(ValueError, match="non_https"):
        check_url("http://jeeadv.ac.in/documents/a.pdf")
    with pytest.raises(ValueError, match="nonofficial"):
        check_url("https://evil-jeeadv.ac.in/a.pdf")
    with pytest.raises(ValueError, match="credentials"):
        check_url("https://user:pass@jeeadv.ac.in/a.pdf")


def test_validate_output_rejects_git_worktree(tmp_path: Path) -> None:
    private = tmp_path / "private-intake"
    private.mkdir()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    with pytest.raises(ValueError, match="git_worktree"):
        validate_private_output_dir(private)


def test_validate_output_rejects_inside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    inner = repo / "nested"
    inner.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="git_worktree"):
        validate_private_output_dir(inner)
    assert validate_private_output_dir(outside, repo_root=repo) == outside.resolve()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_download_six_synthetic_pdfs_writes_receipt(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    pdf = _minimal_pdf()
    mapping = {slot.candidate_url: pdf for slot in build_intake_slots()}
    manifest, code = run_intake(out, opener=_MockOpener(mapping), repo_root=tmp_path / "non-repo")
    assert code == 0
    receipt = out / "eduvijna-d12-2026-intake-UNAPPROVED.json"
    assert receipt.exists()
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["manifest_kind"] == MANIFEST_KIND
    assert data["official_reference_ready"] is False
    assert data["human_curator_approval"] is False
    assert len(data["source_slots"]) == 6
    digest = hashlib.sha256(pdf).hexdigest()
    for row in data["source_slots"]:
        assert row["sha256_exact_downloaded_bytes"] == digest
        assert row["rights_review_status"] == "PENDING_HUMAN_LEGAL_REVIEW"
        assert row["copyright_reuse_permission"] == "NOT_DETERMINED"
        assert row["human_curator_approval"] is False
        assert row["source_authority_status"] == "SOURCE_PENDING"
        assert row["official_reference_ready"] is False
    mode = stat.S_IMODE(out.stat().st_mode)
    assert mode == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


class _OversizeResponse(_ByteResponse):
    def __init__(self, url: str) -> None:
        super().__init__(b"", url)
        self._chunks = 0

    def read(self, size: int = -1) -> bytes:
        self._chunks += 1
        if self._chunks > 55:
            return b""
        return b"x" * CHUNK


CHUNK = 1024 * 1024


class _OversizeOpener:
    def open(self, request: urllib.request.Request, timeout: int = 25) -> _OversizeResponse:
        return _OversizeResponse(request.full_url)


def test_download_rejects_non_pdf_and_oversize(tmp_path: Path) -> None:
    slot = build_intake_slots()[0]
    out = tmp_path / "vault2"
    out.mkdir()
    bad = _MockOpener({slot.candidate_url: b"not-a-pdf" * 10})
    row = download_one(bad, out, slot)
    assert row["download_status"] == "FAILED"
    row2 = download_one(_OversizeOpener(), out, slot)
    assert "pdf_exceeded" in (row2.get("failure_reason") or "")


def test_idempotent_same_bytes_and_conflict_on_change(tmp_path: Path) -> None:
    slot = build_intake_slots()[1]
    out = tmp_path / "vault3"
    out.mkdir()
    pdf_a = _minimal_pdf(b"a")
    pdf_b = _minimal_pdf(b"b")
    opener_a = _MockOpener({slot.candidate_url: pdf_a})
    row1 = download_one(opener_a, out, slot)
    assert row1["download_status"] == "DOWNLOADED_AND_HASHED_UNAPPROVED"
    row2 = download_one(opener_a, out, slot)
    assert row2["sha256_exact_downloaded_bytes"] == row1["sha256_exact_downloaded_bytes"]
    row3 = download_one(_MockOpener({slot.candidate_url: pdf_b}), out, slot)
    assert "existing_pdf_byte_conflict" in (row3.get("failure_reason") or "")


def test_symlink_output_dir_rejected(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link-out"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        validate_private_output_dir(link)


def test_pypdf_unavailable_marks_review_required(tmp_path: Path) -> None:
    slot = build_intake_slots()[2]
    path = tmp_path / slot.private_local_filename
    path.write_bytes(_minimal_pdf())
    with patch.dict("sys.modules", {"pypdf": None}):
        result = inspect_pdf(path, slot)
    assert "REQUIRES_HUMAN_REVIEW" in result["page_inspection"]


def test_manifest_never_sets_official_ready() -> None:
    rows = [{"sha256_exact_downloaded_bytes": "abc", "page_year_warnings": []}]
    manifest = build_manifest(rows)
    assert manifest["official_reference_ready"] is False
    assert manifest["curator_approval"] is False
    text = json.dumps(manifest)
    assert "question" not in text.lower() or "Verify exact" in text


def test_intake_does_not_import_db_staging_modules() -> None:
    import app.jee_advanced.official_source_intake as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "source_ingest_staging" not in source
    assert "sqlalchemy" not in source.lower()