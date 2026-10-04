"""Content checks for a small, reviewed official-source demonstration.

This is not another source ingestion path. It only reads already-ingested Day-3
bytes, verifies their checksum, and locates reviewed short evidence anchors.
No full source text is emitted or committed.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any

from pypdf import PdfReader

from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.source import SourceRevision


def _normalized(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


@dataclass(frozen=True)
class EvidenceAnchor:
    key: str
    source_key: str
    terms: tuple[str, ...]
    page: int | None = None


def check_evidence_anchors(
    service: CurriculumIntelligenceService,
    revisions: dict[str, SourceRevision],
    anchors: list[EvidenceAnchor],
) -> dict[str, Any]:
    """Return exact source identity and page only when every anchor is present.

    All terms must appear on the same PDF page. Fixed reviewed page locators
    stay fixed; text elsewhere cannot silently validate a shifted document.
    """
    checks: list[dict[str, Any]] = []
    for anchor in anchors:
        revision = revisions.get(anchor.source_key)
        check: dict[str, Any] = {
            "key": anchor.key,
            "source_key": anchor.source_key,
            "verified": False,
        }
        checks.append(check)
        if revision is None or not service.has_source_content(revision):
            check["reason"] = "official source content unavailable"
            continue
        check.update(
            source_revision_id=revision.id,
            checksum=revision.checksum,
            source_url=revision.source.url,
        )
        if not revision.storage_path:
            check["reason"] = "original source bytes unavailable"
            continue
        content = service.source_service.storage.read(revision.storage_path)
        if hashlib.sha256(content).hexdigest() != revision.checksum:
            check["reason"] = "stored source checksum mismatch"
            continue
        pages: list[tuple[int | None, str]]
        if revision.content_type == "application/pdf":
            pages = [
                (number + 1, page.extract_text() or "")
                for number, page in enumerate(PdfReader(io.BytesIO(content)).pages)
            ]
        else:
            pages = [(None, revision.extracted_text or "")]
        matches = [
            number
            for number, text in pages
            if (anchor.page is None or number == anchor.page)
            and all(_normalized(term) in _normalized(text) for term in anchor.terms)
        ]
        if not matches:
            check["reason"] = "reviewed evidence anchors not found at expected locator"
            continue
        check.update(verified=True, page=matches[0], matching_pages=matches)
    return {
        "verified": bool(checks) and all(check["verified"] for check in checks),
        "checks": checks,
    }
