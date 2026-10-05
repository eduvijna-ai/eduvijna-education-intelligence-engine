"""Shared actual-byte checks for academic-standard facts and graph references."""

from __future__ import annotations

import io
import re
import unicodedata
from typing import TYPE_CHECKING

from pypdf import PdfReader

from app.curriculum_intelligence.standards_locators import resolve_standard_locator

if TYPE_CHECKING:
    from app.models.source import SourceRevision
    from app.source_intelligence.service import SourceIntelligenceService


class StandardsEvidenceError(ValueError):
    pass


def source_text_at_locator(
    source_service: SourceIntelligenceService,
    revision: SourceRevision,
    *,
    locator: str | None,
) -> str:
    """Prove one bounded location from original approved bytes, never metadata alone."""
    metadata = revision.metadata_json
    manual = metadata.get("manual_metadata", {})
    if (
        revision.status != "active"
        or revision.ingestion_method == "manual"
        or not isinstance(manual, dict)
        or manual.get("registry_only")
        or revision.extraction_status != "succeeded"
        or revision.extracted_checksum != revision.checksum
        or not revision.extracted_text
    ):
        raise StandardsEvidenceError("Evidence requires original source content")
    if not isinstance(locator, str) or not locator.strip():
        raise StandardsEvidenceError("Evidence requires an exact source locator")
    try:
        content, _, valid = source_service._content_integrity(revision)
        if (
            not valid
            or source_service._snapshot_checksum(metadata.get("source_snapshot", {}))
            != revision.source_snapshot_checksum
            or not revision.approval_fingerprint
            or source_service._approval_fingerprint(revision) != revision.approval_fingerprint
        ):
            raise StandardsEvidenceError("Source integrity mismatch")
        if revision.content_type.split(";", 1)[0].strip().lower() == "application/pdf":
            matches = list(re.finditer(r"\bpages?\s*(\d+)(?:\s*[-–]\s*(\d+))?\b", locator, re.I))
            match = matches[0] if len(matches) == 1 else None
            reader = PdfReader(io.BytesIO(content))
            start = int(match.group(1)) if match else 0
            end = int(match.group(2) or start) if match else 0
            if not 1 <= start <= end <= len(reader.pages):
                raise StandardsEvidenceError("Locator must identify one actual PDF page range")
            return "\n".join(reader.pages[i].extract_text() or "" for i in range(start - 1, end))
        return resolve_standard_locator(content, revision.content_type, locator)
    except StandardsEvidenceError:
        raise
    except Exception as exc:
        raise StandardsEvidenceError("Source location unavailable, unbounded or invalid") from exc


def require_source_wording(
    source_service: SourceIntelligenceService,
    revision: SourceRevision,
    *,
    locator: str | None,
    official_text: str | None,
    official_code: str | None = None,
) -> None:
    """Verify original-byte wording at a bounded locator; callers enforce domains."""
    located = source_text_at_locator(source_service, revision, locator=locator)
    words = [value for value in (official_text, official_code) if value is not None]
    if not words or any(not isinstance(value, str) or not value.strip() for value in words):
        raise StandardsEvidenceError("Evidence requires original official text or code")
    if official_text is not None and official_text not in located:
        raise StandardsEvidenceError("Source wording is absent at exact locator")
    if official_code is not None and not contains_complete_identifier(located, official_code):
        raise StandardsEvidenceError(
            "Official code is absent as a complete identifier at exact locator"
        )


def _identifier_character(char: str) -> bool:
    return unicodedata.category(char)[0] in {"L", "M", "N"} or char in "_\u200c\u200d"


def _identifier_spans(text: str, identifier: str) -> list[tuple[int, int]]:
    """Match source codes, not prefixes/suffixes or components of longer codes.

    Unicode letters, marks and joiners count as identifier characters. A dot,
    slash, colon or hyphen joining another identifier component is significant;
    ordinary surrounding punctuation such as '(C-1).' is not part of the code.
    """
    if not identifier or not identifier.strip():
        return []
    spans = []
    for match in re.finditer(re.escape(identifier), text):
        start, end = match.span()
        before = text[start - 1] if start else ""
        after = text[end] if end < len(text) else ""
        if before and _identifier_character(before):
            continue
        if after and _identifier_character(after):
            continue
        if start >= 2 and before in ".-/:" and _identifier_character(text[start - 2]):
            continue
        if end + 1 < len(text) and after in ".-/:" and _identifier_character(text[end + 1]):
            continue
        spans.append((start, end))
    return spans


def contains_complete_identifier(text: str, identifier: str) -> bool:
    return bool(_identifier_spans(text, identifier))


def require_endpoint_mentions(
    text: str,
    *,
    left_codes: tuple[str, ...] = (),
    left_text: str | None = None,
    right_codes: tuple[str, ...] = (),
    right_text: str | None = None,
) -> None:
    """Require distinct source mentions for both endpoints inside the proven quote.

    Callers supply identifiers and original wording already verified against each
    endpoint source. Derived labels and metadata assertions are not source proof.
    A single shared word or one code nested inside another cannot prove two ends.
    """

    def mentions(codes: tuple[str, ...], wording: str | None) -> list[tuple[int, int, str]]:
        spans = [
            (start, end, code)
            for code in codes
            if code
            for start, end in _identifier_spans(text, code)
        ]
        if wording and wording.strip():
            spans.extend((*span, wording) for span in _identifier_spans(text, wording))
        return spans

    left = mentions(left_codes, left_text)
    right = mentions(right_codes, right_text)
    if not any(a[2] != b[2] and (a[1] <= b[0] or b[1] <= a[0]) for a in left for b in right):
        raise StandardsEvidenceError(
            "Bounded relationship quote must identify both endpoints distinctly"
        )


# Retain the standards writer's public API while sharing the same byte/locator
# proof with learning outcomes and independent persisted acceptance.
require_standards_evidence = require_source_wording
