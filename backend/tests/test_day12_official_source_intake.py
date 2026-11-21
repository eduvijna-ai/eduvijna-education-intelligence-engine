"""Offline tests for private official source intake CLI (CORE35-INTAKE)."""

from __future__ import annotations

import io
import json
import os
import stat
import urllib.error
import urllib.request
from http.client import HTTPMessage
from pathlib import Path
from unittest.mock import patch

import pytest

from app.jee_advanced.constants import OFFICIAL_DISCOVERY_URLS
from app.jee_advanced.official_source_intake import (
    MANIFEST_KIND,
    RECEIPT_FILENAME,
    STATUS_FAILED,
    STATUS_REVIEW_REQUIRED,
    OfficialOnlyRedirectHandler,
    build_intake_slots,
    build_manifest,
    check_url,
    download_one,
    inspect_pdf,
    main,
    publish_receipt_exclusive,
    require_absolute_output_dir,
    run_intake,
    validate_private_output_dir,
)

CHUNK = 1024 * 1024


def _minimal_fake_pdf() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<<>>endobj\n"
        b"trailer<<>>\n"
        b"%%EOF\n"
        + b"x" * 8
    )


def _valid_pypdf_bytes() -> bytes | None:
    try:
        from pypdf import PdfWriter
    except ImportError:
        return None
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class _ByteResponse:
    def __init__(
        self,
        data: bytes,
        url: str,
        *,
        content_type: str = "application/pdf",
        content_length: int | None = None,
    ) -> None:
        self._data = data
        self._url = url
        self.headers: dict[str, str] = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

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
    def __init__(self, mapping: dict[str, tuple[bytes, str] | bytes]) -> None:
        self.mapping = mapping

    def open(self, request: urllib.request.Request, timeout: int = 25) -> _ByteResponse:
        url = request.full_url
        if url not in self.mapping:
            raise urllib.error.URLError(f"no mock for {url}")
        raw = self.mapping[url]
        if isinstance(raw, tuple):
            data, ctype = raw
        else:
            data, ctype = raw, "application/pdf"
        return _ByteResponse(data, url, content_type=ctype, content_length=len(data))


def _pdf_mapping(data: bytes) -> dict[str, tuple[bytes, str] | bytes]:
    return {slot.candidate_url: data for slot in build_intake_slots()}


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


def test_main_rejects_relative_output_dir(tmp_path: Path) -> None:
    rel = Path("relative-vault")
    code = main(["--output-dir", str(rel), "--repo-root", str(tmp_path / "non-repo")])
    assert code == 3


def test_require_absolute_output_dir() -> None:
    with pytest.raises(ValueError, match="absolute"):
        require_absolute_output_dir(Path("relative/path"))


def test_check_url_rejects_bad_hosts_and_schemes() -> None:
    with pytest.raises(ValueError, match="non_https"):
        check_url("http://jeeadv.ac.in/documents/a.pdf")
    with pytest.raises(ValueError, match="nonofficial"):
        check_url("https://evil-jeeadv.ac.in/a.pdf")
    with pytest.raises(ValueError, match="credentials"):
        check_url("https://user:pass@jeeadv.ac.in/a.pdf")


def test_redirect_handler_rejects_http_downgrade() -> None:
    handler = OfficialOnlyRedirectHandler()
    req = urllib.request.Request("https://jeeadv.ac.in/documents/a.pdf")
    with pytest.raises(ValueError, match="non_https"):
        handler.redirect_request(req, io.BytesIO(), 302, "", HTTPMessage(), "http://jeeadv.ac.in/b.pdf")


def test_redirect_handler_rejects_lookalike_host() -> None:
    handler = OfficialOnlyRedirectHandler()
    req = urllib.request.Request("https://jeeadv.ac.in/documents/a.pdf")
    with pytest.raises(ValueError, match="nonofficial"):
        handler.redirect_request(
            req,
            io.BytesIO(),
            302,
            "",
            HTTPMessage(),
            "https://jeeadv.ac.in.evil.com/b.pdf",
        )


def test_validate_output_rejects_git_worktree(tmp_path: Path) -> None:
    private = (tmp_path / "private-intake").resolve()
    private.mkdir()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    with pytest.raises(ValueError, match="git_worktree"):
        validate_private_output_dir(private)


def test_validate_output_rejects_symlink_ancestor(tmp_path: Path) -> None:
    target = tmp_path / "real-vault"
    target.mkdir()
    link_parent = tmp_path / "linked"
    link_parent.symlink_to(target, target_is_directory=True)
    child = link_parent / "nested"
    child.mkdir(parents=True)
    with pytest.raises(ValueError, match="symlink"):
        validate_private_output_dir(child)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_receipt_symlink_does_not_modify_outside_sentinel(tmp_path: Path) -> None:
    vault = (tmp_path / "vault").resolve()
    vault.mkdir()
    os.chmod(vault, 0o700)
    sentinel = tmp_path / "outside-sentinel.txt"
    sentinel.write_text("SENTINEL", encoding="utf-8")
    before = sentinel.read_bytes()
    receipt = vault / RECEIPT_FILENAME
    receipt.symlink_to(sentinel)
    manifest = build_manifest([])
    with pytest.raises(ValueError, match="receipt_already_exists"):
        publish_receipt_exclusive(vault, manifest)
    assert sentinel.read_bytes() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_download_six_parseable_pdfs(tmp_path: Path) -> None:
    pdf = _valid_pypdf_bytes() or _minimal_fake_pdf()
    out = (tmp_path / "vault").resolve()
    manifest, code = run_intake(
        out,
        opener=_MockOpener(_pdf_mapping(pdf)),
        repo_root=tmp_path / "non-repo",
    )
    receipt = out / RECEIPT_FILENAME
    assert receipt.exists() and receipt.is_file() and not receipt.is_symlink()
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["manifest_kind"] == MANIFEST_KIND
    assert data["official_reference_ready"] is False
    if _valid_pypdf_bytes():
        assert all(row.get("structure_valid") for row in data["source_slots"])
        assert all(row["sha256_exact_downloaded_bytes"] for row in data["source_slots"])
        # Blank fixture pages have no extractable text → human review, nonzero exit.
        assert code == 2
        assert all(row["download_status"] == STATUS_REVIEW_REQUIRED for row in data["source_slots"])
    else:
        assert code == 2
        assert any(row["download_status"] == STATUS_REVIEW_REQUIRED for row in data["source_slots"])
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    _ = manifest


def test_fake_header_pdf_requires_review_not_success(tmp_path: Path) -> None:
    slot = build_intake_slots()[0]
    out = (tmp_path / "vault-fake").resolve()
    out.mkdir()
    row = download_one(_MockOpener({slot.candidate_url: _minimal_fake_pdf()}), out, slot)
    if row.get("structure_valid"):
        pytest.skip("pypdf accepted minimal stub unexpectedly")
    assert row["download_status"] in {STATUS_REVIEW_REQUIRED, STATUS_FAILED}


def test_html_content_type_rejected(tmp_path: Path) -> None:
    slot = build_intake_slots()[0]
    out = (tmp_path / "vault-html").resolve()
    out.mkdir()
    html = b"<html>not pdf</html>"
    row = download_one(
        _MockOpener({slot.candidate_url: (html, "text/html")}),
        out,
        slot,
    )
    assert row["download_status"] == STATUS_FAILED
    assert "content_type" in (row.get("failure_reason") or "")


def test_content_length_mismatch(tmp_path: Path) -> None:
    slot = build_intake_slots()[0]
    out = (tmp_path / "vault-cl").resolve()
    out.mkdir()
    pdf = _valid_pypdf_bytes() or _minimal_fake_pdf()

    class _WrongLengthResponse(_ByteResponse):
        def __init__(self, data: bytes, url: str) -> None:
            super().__init__(data, url, content_length=len(data) + 10)

    class _LengthOpener:
        def open(self, request: urllib.request.Request, timeout: int = 25) -> _WrongLengthResponse:
            return _WrongLengthResponse(pdf, request.full_url)

    row = download_one(_LengthOpener(), out, slot)  # type: ignore[arg-type]
    assert "content_length_mismatch" in (row.get("failure_reason") or "")


class _OversizeResponse(_ByteResponse):
    def __init__(self, url: str) -> None:
        super().__init__(b"", url)
        self._chunks = 0

    def read(self, size: int = -1) -> bytes:
        self._chunks += 1
        if self._chunks > 55:
            return b""
        return b"x" * CHUNK


class _OversizeOpener:
    def open(self, request: urllib.request.Request, timeout: int = 25) -> _OversizeResponse:
        return _OversizeResponse(request.full_url)


def test_oversize_stream_rejected(tmp_path: Path) -> None:
    slot = build_intake_slots()[0]
    out = (tmp_path / "vault-big").resolve()
    out.mkdir()
    row = download_one(_OversizeOpener(), out, slot)  # type: ignore[arg-type]
    assert "pdf_exceeded" in (row.get("failure_reason") or "")


def test_idempotent_same_bytes_and_conflict_on_change(tmp_path: Path) -> None:
    slot = build_intake_slots()[1]
    out = (tmp_path / "vault-idem").resolve()
    out.mkdir()
    pdf_a = _valid_pypdf_bytes() or _minimal_fake_pdf()
    pdf_b = pdf_a + b"changed"
    opener_a = _MockOpener({slot.candidate_url: pdf_a})
    row1 = download_one(opener_a, out, slot)
    assert row1.get("sha256_exact_downloaded_bytes")
    row2 = download_one(opener_a, out, slot)
    assert row2["sha256_exact_downloaded_bytes"] == row1["sha256_exact_downloaded_bytes"]
    row3 = download_one(_MockOpener({slot.candidate_url: pdf_b}), out, slot)
    assert "existing_pdf_byte_conflict" in (row3.get("failure_reason") or "")


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_destination_pdf_symlink_blocks_write(tmp_path: Path) -> None:
    slot = build_intake_slots()[2]
    out = (tmp_path / "vault-dst").resolve()
    out.mkdir()
    sentinel = tmp_path / "pdf-target.bin"
    sentinel.write_bytes(b"KEEP")
    dest = out / slot.private_local_filename
    dest.symlink_to(sentinel)
    pdf = _valid_pypdf_bytes() or _minimal_fake_pdf()
    row = download_one(_MockOpener({slot.candidate_url: pdf}), out, slot)
    assert row["download_status"] == STATUS_FAILED
    assert sentinel.read_bytes() == b"KEEP"


def test_pypdf_unavailable_marks_review_required(tmp_path: Path) -> None:
    slot = build_intake_slots()[2]
    path = tmp_path / slot.private_local_filename
    path.write_bytes(_minimal_fake_pdf())
    with patch.dict("sys.modules", {"pypdf": None}):
        result = inspect_pdf(path, slot)
    assert "REQUIRES_HUMAN_REVIEW" in result["page_inspection"]
    assert not result["structure_valid"]


def test_manifest_never_sets_official_ready() -> None:
    rows = [{"sha256_exact_downloaded_bytes": "abc", "page_year_warnings": []}]
    manifest = build_manifest(rows)
    assert manifest["official_reference_ready"] is False
    assert manifest["curator_approval"] is False


def test_intake_does_not_import_db_staging_modules() -> None:
    import app.jee_advanced.official_source_intake as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "source_ingest_staging" not in source
    assert "sqlalchemy" not in source.lower()