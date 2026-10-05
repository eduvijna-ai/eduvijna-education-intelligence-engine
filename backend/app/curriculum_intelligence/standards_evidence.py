"""Shared actual-byte checks for academic-standard facts and graph references."""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

from pypdf import PdfReader

from app.curriculum_intelligence.standards_locators import resolve_standard_locator

if TYPE_CHECKING:
    from app.models.source import SourceRevision
    from app.source_intelligence.service import SourceIntelligenceService


class StandardsEvidenceError(ValueError):
    pass


def require_standards_evidence(
    source_service: SourceIntelligenceService,
    revision: SourceRevision,
    *,
    locator: str | None,
    official_text: str | None,
    official_code: str | None = None,
) -> None:
    metadata = revision.metadata_json
    if (
        revision.status != "active"
        or revision.ingestion_method == "manual"
        or metadata.get("manual_metadata", {}).get("registry_only")
        or revision.extraction_status != "succeeded"
        or revision.extracted_checksum != revision.checksum
        or not revision.extracted_text
    ):
        raise StandardsEvidenceError("Academic standards require original source content")
    if not locator or not locator.strip():
        raise StandardsEvidenceError("Academic standards require an exact source locator")
    words = [value for value in (official_text, official_code) if value is not None]
    if not words or any(not isinstance(value, str) or not value.strip() for value in words):
        raise StandardsEvidenceError("Academic standards require original official text or code")
    try:
        content, _, valid = source_service._content_integrity(revision)
        if (
            not valid
            or source_service._snapshot_checksum(metadata.get("source_snapshot", {}))
            != revision.source_snapshot_checksum
            or not revision.approval_fingerprint
            or source_service._approval_fingerprint(revision) != revision.approval_fingerprint
        ):
            raise StandardsEvidenceError("Academic standards source integrity mismatch")
        if revision.content_type.split(";", 1)[0].strip().lower() == "application/pdf":
            match = re.search(r"\bpages?\s*(\d+)(?:\s*[-–]\s*(\d+))?\b", locator, re.I)
            reader = PdfReader(io.BytesIO(content))
            start = int(match.group(1)) if match else 0
            end = int(match.group(2) or start) if match else 0
            if not 1 <= start <= end <= len(reader.pages):
                raise StandardsEvidenceError("Standards locator must identify actual PDF pages")
            located = "\n".join(reader.pages[i].extract_text() or "" for i in range(start - 1, end))
        else:
            located = resolve_standard_locator(content, revision.content_type, locator)
        if any(word not in located for word in words):
            raise StandardsEvidenceError("Standards wording is absent at exact locator")
    except StandardsEvidenceError:
        raise
    except Exception as exc:
        raise StandardsEvidenceError("Standards source content unavailable or invalid") from exc
