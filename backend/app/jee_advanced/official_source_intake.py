"""Private opt-in CLI intake for six JEE Advanced 2026 discovery PDFs (CORE #35).

Captures bytes and an UNAPPROVED receipt only. Never activates SourceRevision,
curator approval, or reference mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPMessage
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlparse

from app.jee_advanced.constants import (
    JEE_ADVANCED_OFFICIAL_HOST,
    OFFICIAL_DISCOVERY_URLS,
)
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS

MANIFEST_KIND = "EDUVIJNA_D12_2026_PRIVATE_INTAKE_UNAPPROVED"
RECEIPT_FILENAME = "eduvijna-d12-2026-intake-UNAPPROVED.json"
MAX_BYTES = 50 * 1024 * 1024
ALLOWED_HOST = JEE_ADVANCED_OFFICIAL_HOST
CHUNK_SIZE = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 25
PAPER1_URL_VERIFICATION_NOTE = (
    "Paper1 discovery URL may serve inconsistent 2025/2026 headers; "
    "human visual page review required before any official pin."
)

STATUS_INTAKE_CAPTURED = "INTAKE_CAPTURED_UNAPPROVED"
STATUS_REVIEW_REQUIRED = "REQUIRES_HUMAN_REVIEW"
STATUS_FAILED = "FAILED"

_URL_KEY_BY_SLOT: dict[str, str] = {
    "jee_advanced.2026.brochure": "brochure_en_2026",
    "jee_advanced.2026.syllabus": "syllabus_2026",
    "jee_advanced.2026.paper_1": "paper1_en_2026",
    "jee_advanced.2026.paper_2": "paper2_en_2026",
    "jee_advanced.2026.key_paper_1": "key_paper1_final_2026",
    "jee_advanced.2026.key_paper_2": "key_paper2_final_2026",
}


@dataclass(frozen=True, slots=True)
class IntakeSlot:
    slot_id: str
    document_role: str
    paper_code: str | None
    candidate_url: str
    private_local_filename: str
    expected_year: int = 2026


def build_intake_slots() -> tuple[IntakeSlot, ...]:
    slots: list[IntakeSlot] = []
    for descriptor in JEE_ADVANCED_2026_SOURCE_SLOTS:
        url_key = _URL_KEY_BY_SLOT.get(descriptor.slot_id)
        if not url_key:
            continue
        url = OFFICIAL_DISCOVERY_URLS.get(url_key)
        if not url:
            continue
        filename = Path(urlparse(url).path).name
        slots.append(
            IntakeSlot(
                slot_id=descriptor.slot_id,
                document_role=descriptor.document_role,
                paper_code=descriptor.paper_code,
                candidate_url=url,
                private_local_filename=filename,
            )
        )
    if len(slots) != 6:
        raise RuntimeError("intake_slot_catalog_incomplete")
    return tuple(slots)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("refusing_non_https_url")
    host = (parsed.hostname or "").lower()
    if host != ALLOWED_HOST:
        raise ValueError("refusing_nonofficial_host")
    if parsed.username or parsed.password:
        raise ValueError("refusing_url_with_credentials")
    if parsed.port not in (None, 443):
        raise ValueError("refusing_nonstandard_port")


class OfficialOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _path_has_symlink_component(path: Path) -> bool:
    for component in [path, *path.parents]:
        if component.is_symlink():
            return True
    return False


def require_absolute_output_dir(output_dir: Path) -> Path:
    expanded = output_dir.expanduser()
    if not expanded.is_absolute():
        raise ValueError("output_dir_must_be_absolute")
    return expanded


def validate_private_output_dir(output_dir: Path, *, repo_root: Path | None = None) -> Path:
    absolute = require_absolute_output_dir(output_dir)
    if _path_has_symlink_component(absolute):
        raise ValueError("output_path_symlink_forbidden")
    resolved = absolute.resolve(strict=False)
    if _path_has_symlink_component(resolved):
        raise ValueError("output_resolves_through_symlink")
    if resolved.name == ".git" or ".git" in resolved.parts:
        raise ValueError("output_inside_git_directory")
    for parent in [resolved, *resolved.parents]:
        if (parent / ".git").exists():
            raise ValueError("output_inside_git_worktree")
    if repo_root is not None:
        repo = repo_root.resolve()
        try:
            resolved.relative_to(repo)
            raise ValueError("output_inside_repository_tree")
        except ValueError as exc:
            if "output_inside_repository_tree" in str(exc):
                raise
    return resolved


def _content_type_allowed(content_type: str) -> bool:
    primary = (content_type or "").split(";", 1)[0].strip().lower()
    return primary in {"application/pdf", "application/x-pdf"}


def _open_exclusive(path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags, 0o600)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_bytes_exclusive(dest: Path, source: Path) -> None:
    if dest.exists() or dest.is_symlink():
        raise ValueError("destination_already_exists")
    fd = _open_exclusive(dest)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as src:
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
    except Exception:
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise
    os.chmod(dest, 0o600)


def _reconcile_or_publish_pdf(dest: Path, temp_path: Path) -> str:
    """Return 'created', 'identical', or raise on conflict/symlink."""

    if dest.is_symlink():
        raise ValueError("destination_is_symlink")
    if dest.exists():
        if not dest.is_file():
            raise ValueError("destination_not_regular_file")
        if _file_sha256(dest) != _file_sha256(temp_path):
            raise ValueError("existing_pdf_byte_conflict")
        return "identical"
    _publish_bytes_exclusive(dest, temp_path)
    return "created"


def _write_temp_in_vault(output_dir: Path) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    name = f".eduvijna-intake-{os.getpid()}-{utc_now().replace(':', '')}.tmp"
    target = output_dir / name
    fd = os.open(target, flags, 0o600)
    return fd, target


def inspect_pdf_structure_and_headers(path: Path, slot: IntakeSlot) -> dict[str, Any]:
    result: dict[str, Any] = {
        "page_count": None,
        "page_year_warnings": [],
        "page_inspection": "NOT_RUN",
        "structure_valid": False,
        "requires_human_review": True,
    }
    try:
        from pypdf import PdfReader
    except ImportError:
        result["page_inspection"] = "PYPDF_UNAVAILABLE_REQUIRES_HUMAN_REVIEW"
        return result
    try:
        reader = PdfReader(str(path), strict=True)
        if reader.is_encrypted:
            result["page_inspection"] = "ENCRYPTED_REQUIRES_HUMAN_REVIEW"
            return result
        pages = reader.pages
        result["page_count"] = len(pages)
        if not pages:
            result["page_inspection"] = "EMPTY_PDF_REJECTED"
            return result
        result["structure_valid"] = True
        text_empty = 0
        year_roles = {"question_paper", "final_answer_key"}
        for index, page in enumerate(pages):
            text = (page.extract_text() or "").strip()
            if not text:
                text_empty += 1
                continue
            if slot.document_role in year_roles:
                header = re.sub(r"\s+", " ", text[:240])
                found = re.search(r"JEE\s*\(?Advanced\)?\s*(20\d{2})", header, re.IGNORECASE)
                if found and found.group(1) != str(slot.expected_year):
                    result["page_year_warnings"].append(
                        {"page_1_based": index + 1, "year_seen": found.group(1)}
                    )
        result["pages_without_extractable_text"] = text_empty
        result["page_inspection"] = "TEXT_INSPECTED_NOT_CURATOR_APPROVED"
        if text_empty == len(pages):
            result["requires_human_review"] = True
        elif result["page_year_warnings"]:
            result["requires_human_review"] = True
        else:
            result["requires_human_review"] = False
    except Exception as exc:
        result["page_inspection"] = f"STRUCTURE_INVALID:{type(exc).__name__}:{str(exc)[:120]}"
        result["structure_valid"] = False
    return result


def inspect_pdf(path: Path, slot: IntakeSlot) -> dict[str, Any]:
    return inspect_pdf_structure_and_headers(path, slot)


def _base_row(slot: IntakeSlot) -> dict[str, Any]:
    return {
        "slot_id": slot.slot_id,
        "document_role": slot.document_role,
        "expected_year": slot.expected_year,
        "candidate_url": slot.candidate_url,
        "final_url": None,
        "retrieved_utc": None,
        "sha256_exact_downloaded_bytes": None,
        "file_size_bytes": None,
        "private_local_filename": slot.private_local_filename,
        "download_status": STATUS_FAILED,
        "original_source_revision_id": None,
        "rights_review_status": "PENDING_HUMAN_LEGAL_REVIEW",
        "copyright_reuse_permission": "NOT_DETERMINED",
        "human_curator_approval": False,
        "approved_exam_blueprint_rule_ids": [],
        "source_authority_status": "SOURCE_PENDING",
        "official_reference_ready": False,
    }


def _classify_row_after_inspection(row: dict[str, Any], inspection: dict[str, Any]) -> None:
    row.update(inspection)
    if not _content_type_allowed(str(row.get("http_content_type") or "")):
        row["download_status"] = STATUS_REVIEW_REQUIRED
        row["content_type_rejected"] = True
        return
    if not inspection.get("structure_valid"):
        row["download_status"] = STATUS_REVIEW_REQUIRED
        return
    if inspection.get("page_inspection") == "EMPTY_PDF_REJECTED":
        row["download_status"] = STATUS_FAILED
        return
    if inspection.get("page_year_warnings"):
        row["download_status"] = STATUS_REVIEW_REQUIRED
        return
    if inspection.get("requires_human_review"):
        row["download_status"] = STATUS_REVIEW_REQUIRED
        return
    row["download_status"] = STATUS_INTAKE_CAPTURED


def download_one(
    opener: urllib.request.OpenerDirector,
    output_dir: Path,
    slot: IntakeSlot,
) -> dict[str, Any]:
    url = slot.candidate_url
    check_url(url)
    row = _base_row(slot)
    if slot.slot_id.endswith(".paper_1"):
        row["discovery_verification_note"] = PAPER1_URL_VERIFICATION_NOTE
    dest = output_dir / slot.private_local_filename
    temp_path: Path | None = None
    fd: int | None = None
    try:
        if dest.is_symlink():
            raise ValueError("destination_is_symlink")
        request = urllib.request.Request(url, headers={"User-Agent": "Eduvijna-SourceIntake/1.0"})
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final = response.geturl()
            check_url(final)
            row["final_url"] = final
            content_type = response.headers.get("Content-Type", "")
            row["http_content_type"] = content_type
            row["http_last_modified"] = response.headers.get("Last-Modified")
            row["http_etag"] = response.headers.get("ETag")
            if not _content_type_allowed(content_type):
                raise ValueError("http_content_type_not_pdf")
            content_length_raw = response.headers.get("Content-Length")
            expected_length: int | None = None
            if content_length_raw:
                expected_length = int(content_length_raw)
                if expected_length > MAX_BYTES:
                    raise ValueError("content_length_exceeds_limit")
            digest = hashlib.sha256()
            size = 0
            fd, temp_path = _write_temp_in_vault(output_dir)
            with os.fdopen(fd, "wb") as temp:
                fd = None
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("pdf_exceeded_size_limit")
                    digest.update(chunk)
                    temp.write(chunk)
            if expected_length is not None and size != expected_length:
                raise ValueError("content_length_mismatch")
        assert temp_path is not None
        with temp_path.open("rb") as handle:
            first = handle.read(8)
            if temp_path.stat().st_size < 30:
                raise ValueError("too_small_for_pdf")
            handle.seek(max(0, temp_path.stat().st_size - 4096))
            tail = handle.read()
        if not first.startswith(b"%PDF-") or b"%%EOF" not in tail:
            raise ValueError("pdf_header_trailer_invalid")
        action = _reconcile_or_publish_pdf(dest, temp_path)
        if action == "identical":
            temp_path.unlink(missing_ok=True)
            temp_path = None
        else:
            temp_path.unlink(missing_ok=True)
            temp_path = None
        row.update(
            {
                "retrieved_utc": utc_now(),
                "sha256_exact_downloaded_bytes": digest.hexdigest(),
                "file_size_bytes": size,
            }
        )
        inspection = inspect_pdf_structure_and_headers(dest, slot)
        _classify_row_after_inspection(row, inspection)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        row["failure_reason"] = f"{type(exc).__name__}:{str(exc)[:240]}"
        row["download_status"] = STATUS_FAILED
    finally:
        if fd is not None:
            os.close(fd)
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return row


def build_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    captured = sum(1 for row in rows if row.get("download_status") == STATUS_INTAKE_CAPTURED)
    return {
        "manifest_kind": MANIFEST_KIND,
        "created_utc": utc_now(),
        "warning": (
            "Private intake capture only. Not rights grant, curator approval, "
            "SourceAuditEvent, or activated Day3 revision."
        ),
        "curator_approval": False,
        "human_curator_approval": False,
        "official_reference_ready": False,
        "expected_slot_count": len(rows),
        "intake_captured_unapproved": captured,
        "downloaded_hashed": sum(1 for row in rows if row.get("sha256_exact_downloaded_bytes")),
        "source_slots": rows,
        "human_followup": [
            "Verify exact 2026 title/year/paper on EVERY rendered page of EACH file",
            "Record page locators and scoring; obtain written legal rights determination",
            "Stage bytes privately via Day3 SourceRevision workflow with curator audit",
            "Never treat this manifest as authorized IIT/JAB examination approval",
        ],
    }


def compute_intake_exit_code(rows: list[dict[str, Any]]) -> int:
    if any(row.get("download_status") == STATUS_FAILED for row in rows):
        return 2
    if any(row.get("download_status") == STATUS_REVIEW_REQUIRED for row in rows):
        return 2
    if all(row.get("download_status") == STATUS_INTAKE_CAPTURED for row in rows):
        return 0
    return 2


def publish_receipt_exclusive(vault: Path, manifest: dict[str, Any]) -> Path:
    receipt_path = vault / RECEIPT_FILENAME
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError("receipt_already_exists")
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = _open_exclusive(receipt_path)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except Exception:
        try:
            os.unlink(receipt_path)
        except OSError:
            pass
        raise
    os.chmod(receipt_path, stat.S_IMODE(0o600))
    return receipt_path


def run_intake(
    output_dir: Path,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    repo_root: Path | None = None,
    write_receipt: bool = True,
) -> tuple[dict[str, Any], int]:
    resolved = validate_private_output_dir(output_dir, repo_root=repo_root)
    os.umask(0o077)
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    active_opener = opener or urllib.request.build_opener(OfficialOnlyRedirectHandler())
    rows = [download_one(active_opener, resolved, slot) for slot in build_intake_slots()]
    manifest = build_manifest(rows)
    if write_receipt:
        publish_receipt_exclusive(resolved, manifest)
    exit_code = compute_intake_exit_code(rows)
    return manifest, exit_code


def print_list_only() -> int:
    for slot in build_intake_slots():
        print(f"{slot.slot_id}\t{slot.document_role}\t{slot.candidate_url}")
    return 0


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Private intake of six public JEE Advanced 2026 PDF discovery links. "
            "NOT copyright approval, NOT curator signoff, NOT database activation."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Absolute private folder OUTSIDE any Git worktree for PDF bytes and receipt",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print six registered official discovery URLs; no network and no files",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root(),
        help="Repository root used to refuse output inside the checkout (default: auto)",
    )
    args = parser.parse_args(argv)
    if args.list_only:
        return print_list_only()
    if args.output_dir is None:
        parser.error("--output-dir is required unless --list-only is set")
    try:
        require_absolute_output_dir(args.output_dir)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    # Merge-safety quarantine: preserve the offline harness and discovery command,
    # but do not expose the known unsafe vault publication path to operators.
    print(
        "REFUSED: live private-source intake disabled pending security review. "
        "Use --list-only; no download or receipt was written.",
        file=sys.stderr,
    )
    return 3