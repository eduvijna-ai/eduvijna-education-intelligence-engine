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
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPMessage
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, Any
from urllib.parse import urlparse

from app.jee_advanced.constants import (
    JEE_ADVANCED_OFFICIAL_HOST,
    OFFICIAL_DISCOVERY_URLS,
)
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS

MANIFEST_KIND = "EDUVIJNA_D12_2026_PRIVATE_INTAKE_UNAPPROVED"
MAX_BYTES = 50 * 1024 * 1024
ALLOWED_HOST = JEE_ADVANCED_OFFICIAL_HOST
CHUNK_SIZE = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 25
PAPER1_URL_VERIFICATION_NOTE = (
    "Paper1 discovery URL may serve inconsistent 2025/2026 headers; "
    "human visual page review required before any official pin."
)

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
    """Six canonical slots aligned with Day12 registry and discovery URLs."""

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


def validate_private_output_dir(output_dir: Path, *, repo_root: Path | None = None) -> Path:
    resolved = output_dir.expanduser()
    if resolved.is_symlink():
        raise ValueError("output_dir_symlink_forbidden")
    resolved = resolved.resolve()
    if resolved.is_symlink():
        raise ValueError("output_resolves_to_symlink")
    if resolved.name == ".git" or ".git" in resolved.parts:
        raise ValueError("output_inside_git_directory")
    for parent in [resolved, *resolved.parents]:
        git_mark = parent / ".git"
        if git_mark.exists():
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


def inspect_pdf(path: Path, slot: IntakeSlot) -> dict[str, Any]:
    """Optional per-page text header checking; human review still required."""

    result: dict[str, Any] = {
        "page_count": None,
        "page_year_warnings": [],
        "page_inspection": "NOT_RUN",
    }
    try:
        from pypdf import PdfReader
    except ImportError:
        result["page_inspection"] = "PYPDF_UNAVAILABLE_REQUIRES_HUMAN_REVIEW"
        return result
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            result["page_inspection"] = "ENCRYPTED_REQUIRES_HUMAN_REVIEW"
            return result
        result["page_count"] = len(reader.pages)
        if not reader.pages:
            result["page_inspection"] = "EMPTY_PDF_REJECTED"
            return result
        text_empty = 0
        year_roles = {"question_paper", "final_answer_key"}
        for index, page in enumerate(reader.pages):
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
    except Exception as exc:
        result["page_inspection"] = f"INSPECTION_ERROR:{type(exc).__name__}:{str(exc)[:160]}"
    return result


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
        "download_status": "FAILED",
        "original_source_revision_id": None,
        "rights_review_status": "PENDING_HUMAN_LEGAL_REVIEW",
        "copyright_reuse_permission": "NOT_DETERMINED",
        "human_curator_approval": False,
        "approved_exam_blueprint_rule_ids": [],
        "source_authority_status": "SOURCE_PENDING",
        "official_reference_ready": False,
    }


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
    if dest.is_symlink():
        row["failure_reason"] = "ValueError:destination_is_symlink"
        return row
    temp_path: Path | None = None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Eduvijna-SourceIntake/1.0"})
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final = response.geturl()
            check_url(final)
            row["final_url"] = final
            row["http_content_type"] = response.headers.get("Content-Type", "")
            row["http_last_modified"] = response.headers.get("Last-Modified")
            row["http_etag"] = response.headers.get("ETag")
            digest = hashlib.sha256()
            size = 0
            with NamedTemporaryFile(
                prefix=".eduvijna-intake-",
                dir=output_dir,
                delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("pdf_exceeded_size_limit")
                    digest.update(chunk)
                    temp.write(chunk)
        if temp_path is None:
            raise ValueError("missing_temporary_download")
        with temp_path.open("rb") as handle:
            first = handle.read(8)
            if temp_path.stat().st_size < 30:
                raise ValueError("too_small_for_pdf")
            handle.seek(max(0, temp_path.stat().st_size - 4096))
            tail = handle.read()
        if not first.startswith(b"%PDF-") or b"%%EOF" not in tail:
            raise ValueError("pdf_header_trailer_invalid")
        os.chmod(temp_path, 0o600)
        if dest.exists():
            if dest.is_symlink():
                raise ValueError("destination_is_symlink")
            existing = hashlib.sha256()
            with dest.open("rb") as saved:
                for chunk in iter(lambda: saved.read(CHUNK_SIZE), b""):
                    existing.update(chunk)
            if existing.hexdigest() != digest.hexdigest():
                raise ValueError("existing_pdf_byte_conflict")
            temp_path.unlink()
            temp_path = None
        else:
            temp_path.replace(dest)
        os.chmod(dest, 0o600)
        row.update(
            {
                "download_status": "DOWNLOADED_AND_HASHED_UNAPPROVED",
                "retrieved_utc": utc_now(),
                "sha256_exact_downloaded_bytes": digest.hexdigest(),
                "file_size_bytes": size,
            }
        )
        row.update(inspect_pdf(dest, slot))
        if row.get("page_year_warnings"):
            row["download_status"] = "YEAR_MISMATCH_REQUIRES_REVIEW"
        if row.get("page_inspection") == "EMPTY_PDF_REJECTED":
            row["download_status"] = "EMPTY_PDF_REJECTED"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        row["failure_reason"] = f"{type(exc).__name__}:{str(exc)[:240]}"
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return row


def build_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    downloaded = sum(1 for row in rows if row.get("sha256_exact_downloaded_bytes"))
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
        "downloaded_hashed": downloaded,
        "source_slots": rows,
        "human_followup": [
            "Verify exact 2026 title/year/paper on EVERY rendered page of EACH file",
            "Record page locators and scoring; obtain written legal rights determination",
            "Stage bytes privately via Day3 SourceRevision workflow with curator audit",
            "Never treat this manifest as authorized IIT/JAB examination approval",
        ],
    }


def run_intake(
    output_dir: Path,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any], int]:
    resolved = validate_private_output_dir(output_dir, repo_root=repo_root)
    os.umask(0o077)
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    active_opener = opener or urllib.request.build_opener(OfficialOnlyRedirectHandler())
    rows = [download_one(active_opener, resolved, slot) for slot in build_intake_slots()]
    manifest = build_manifest(rows)
    receipt_path = resolved / "eduvijna-d12-2026-intake-UNAPPROVED.json"
    receipt_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(receipt_path, 0o600)
    exit_code = (
        0
        if manifest["downloaded_hashed"] == manifest["expected_slot_count"]
        and not any(row.get("page_year_warnings") for row in rows)
        else 2
    )
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
        manifest, code = run_intake(args.output_dir, repo_root=args.repo_root)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    receipt = args.output_dir.expanduser().resolve() / "eduvijna-d12-2026-intake-UNAPPROVED.json"
    print(f"Receipt: {receipt}")
    print("CAUTION: SOURCE_PENDING. RIGHTS_AND_CURATOR_APPROVAL_NOT_GIVEN.", file=sys.stderr)
    for row in manifest.get("source_slots") or []:
        print(f"{row.get('download_status')}: {row.get('slot_id')}", file=sys.stderr)
    return code