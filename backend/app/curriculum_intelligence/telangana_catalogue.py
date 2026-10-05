"""Build scoped catalogue snapshots from reviewed Telangana syllabus inventories."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urljoin, urlsplit

from app.curriculum_intelligence.scoped_catalogue import (
    UNKNOWN,
    CatalogueSnapshot,
    ScopedCatalogueRow,
    checked_text,
)
from app.curriculum_intelligence.telangana_syllabus import ParsedSyllabus

if TYPE_CHECKING:
    from app.models.curriculum import CurriculumVersion
    from app.models.source import SourceRevision


def syllabus_catalogue_snapshot(
    *,
    pack_id: str,
    version_id: str,
    revision: SourceRevision,
    parsed: ParsedSyllabus,
    grade: str,
    medium: str,
    academic_year: str,
) -> CatalogueSnapshot:
    rows = [
        ScopedCatalogueRow(
            pack_id=pack_id,
            version_id=version_id,
            source_revision_id=revision.id,
            source_checksum=revision.checksum,
            source_locator=f"{parsed.subject_label} syllabus inventory",
            official_label=parsed.subject_label,
            grade=grade,
            academic_year=academic_year,
            instructional_medium=medium,
            subject_language=medium,
            resource_kind="syllabus_document",
            document_content_status="reviewed",
        )
    ]
    for chapter in parsed.chapters:
        rows.append(
            ScopedCatalogueRow(
                pack_id=pack_id,
                version_id=version_id,
                source_revision_id=revision.id,
                source_checksum=revision.checksum,
                source_locator=chapter.locator,
                official_label=f"{chapter.number}. {chapter.title}",
                grade=grade,
                academic_year=academic_year,
                instructional_medium=medium,
                subject_language=medium,
                resource_kind="syllabus_document",
                document_content_status="reviewed",
            )
        )
    return CatalogueSnapshot(
        source_revision_id=revision.id,
        source_checksum=revision.checksum,
        rows=tuple(rows),
        extraction_method="telangana-syllabus-inventory",
        inventory_status="complete",
    )


def pack_catalogue_report(
    *,
    pack_code: str,
    version: CurriculumVersion,
    snapshot: CatalogueSnapshot,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pack_code": pack_code,
        "version_id": version.id,
        "source_completeness_verified": True,
        "synthetic": False,
        "coverage": {
            "status": snapshot.inventory_status,
            "snapshot_row_count": len(snapshot.rows),
            "materialized_metadata_count": coverage.get("materialized_metadata_count", 0),
            "missing_ids": coverage.get("missing_ids", []),
            "unexpected_ids": coverage.get("unexpected_ids", []),
            "duplicate_ids": coverage.get("duplicate_ids", []),
            "conflicting_ids": coverage.get("conflicting_ids", []),
        },
    }


_ROMAN_GRADES = {
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "6": "VI",
    "7": "VII",
    "8": "VIII",
    "9": "IX",
    "10": "X",
}
_SCERT_MEDIA = ("Telugu", "English", "Urdu", "Hindi", "Kannada", "Marathi", "Tamil")
_LANGUAGE_TOKENS = {
    "TEL": "Telugu",
    "URD": "Urdu",
    "HIN": "Hindi",
    "SAN": "Sanskrit",
    "KAN": "Kannada",
    "KND": "Kannada",
    "MAR": "Marathi",
    "TAM": "Tamil",
    "TML": "Tamil",
    "ENG": "English",
}


class _ScertCatalogueHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None
        self._anchor: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {"text": [], "anchors": []}
        elif tag == "a" and self._cell is not None:
            self._anchor = {"href": dict(attrs).get("href") or "", "text": []}

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"].append(data)
        if self._anchor is not None:
            self._anchor["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None and self._cell is not None:
            self._cell["anchors"].append(self._anchor)
            self._anchor = None
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None
            self._anchor = None


def _catalogue_text(parts: list[str]) -> str:
    value = " ".join(" ".join(parts).replace("\xa0", " ").split())
    return checked_text(value) if value else ""


def _grade_from_text(value: str) -> str | None:
    match = re.fullmatch(r"\s*(10|[1-9])(?:st|nd|rd|th)?\s*", value, re.I)
    return _ROMAN_GRADES.get(match.group(1)) if match else None


def _medium_from_text(value: str) -> str | None:
    normalized = value.strip().casefold()
    for medium in _SCERT_MEDIA:
        if normalized == medium.casefold():
            return medium
    return None


def _subject_language(label: str, header: str, medium: str) -> str:
    upper = re.sub(r"[^A-Z0-9]+", "_", label.upper())
    for token, language in _LANGUAGE_TOKENS.items():
        if re.search(rf"(?:^|_){token}(?:_|$)", upper):
            return language
    if header.casefold() == "english":
        return "English"
    if header.casefold() == "first language":
        return medium
    return UNKNOWN


def _language_role(header: str) -> str:
    normalized = header.casefold()
    if normalized == "first language":
        return "first"
    if normalized in {"maths", "physical science", "biological science", "social", "social studies", "environmental education"}:
        return "not_applicable"
    return "unknown"


def _book_part(label: str) -> str:
    match = re.search(r"\bpart\s*[- ]?(1|2)\b", label, re.I)
    return f"Part {match.group(1)}" if match else UNKNOWN


def _anchor_label(anchor: dict[str, Any], header: str) -> str:
    label = _catalogue_text(list(anchor.get("text") or []))
    if not label:
        path = unquote(urlsplit(str(anchor.get("href") or "")).path)
        label = path.rsplit("/", 1)[-1] or header
    if re.fullmatch(r"part\s*[- ]?[12]", label, re.I):
        return checked_text(f"{header} {label}")
    return checked_text(label)


def scert_textbook_catalogue_snapshot(
    *,
    content: bytes,
    source_url: str,
    pack_id: str,
    version_id: str,
    revision: SourceRevision,
    academic_year: str,
) -> CatalogueSnapshot:
    """Normalize the official SCERT I-X textbook HTML catalogue.

    This adapter records catalogue metadata only. It does not create syllabus
    membership and does not infer academic applicability beyond the explicit
    catalogue year.
    """
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise ValueError("SCERT catalogue HTML must be valid UTF-8") from exc

    parser = _ScertCatalogueHTMLParser()
    parser.feed(text)
    parser.close()

    headers: list[str] = []
    last_grade: str | None = None
    last_medium: str | None = None
    rows: list[ScopedCatalogueRow] = []
    seen_urls: set[tuple[str, str, str, str]] = set()
    grades_seen: set[str] = set()

    for row_index, cells in enumerate(parser.rows, start=1):
        texts = [_catalogue_text(list(cell.get("text") or [])) for cell in cells]
        if "First Language" in texts and ("Maths" in texts or "Mathematics" in texts):
            first = texts.index("First Language")
            headers = [value for value in texts[first:] if value]
            continue
        if not headers:
            continue

        grade_index = next(
            (index for index, value in enumerate(texts) if _grade_from_text(value)),
            None,
        )
        if grade_index is not None:
            last_grade = _grade_from_text(texts[grade_index])
        medium_index = next(
            (index for index, value in enumerate(texts) if _medium_from_text(value)),
            None,
        )
        if medium_index is not None:
            last_medium = _medium_from_text(texts[medium_index])
        if last_grade is None or last_medium is None:
            continue
        grades_seen.add(last_grade)

        if medium_index is not None:
            subject_cells = cells[medium_index + 1 :]
        elif len(cells) >= len(headers):
            subject_cells = cells[-len(headers) :]
        else:
            continue

        for subject_index, cell in enumerate(subject_cells):
            if subject_index >= len(headers):
                break
            header = checked_text(headers[subject_index])
            cell_text = _catalogue_text(list(cell.get("text") or []))
            for anchor in cell.get("anchors") or []:
                href = str(anchor.get("href") or "").strip()
                if not href or href.startswith(("#", "javascript:")):
                    continue
                resource_url = urljoin(source_url, href)
                label = _anchor_label(anchor, header)
                dedupe = (last_grade, last_medium, header, resource_url)
                if dedupe in seen_urls:
                    continue
                seen_urls.add(dedupe)
                combined = f"{cell_text} {label}"
                part = _book_part(combined)
                bilingual = "yes" if "bilingual" in combined.casefold() else "no"
                rows.append(
                    ScopedCatalogueRow(
                        pack_id=pack_id,
                        version_id=version_id,
                        source_revision_id=revision.id,
                        source_checksum=revision.checksum,
                        source_locator=checked_text(
                            f"SCERT textbook catalogue row {row_index} > "
                            f"{last_grade} > {last_medium} > {header} > {label}"
                        ),
                        official_label=label,
                        resource_url=resource_url,
                        grade=last_grade,
                        academic_year=academic_year,
                        instructional_medium=last_medium,
                        subject_language=_subject_language(label, header, last_medium),
                        language_role=_language_role(header),
                        book_part=part,
                        bilingual=bilingual,
                        resource_kind="textbook",
                        document_content_status="not_parsed",
                    )
                )

    if not rows:
        raise ValueError("SCERT textbook catalogue contained no usable resource links")
    expected = set(_ROMAN_GRADES.values())
    return CatalogueSnapshot(
        source_revision_id=revision.id,
        source_checksum=revision.checksum,
        rows=tuple(rows),
        extraction_method="scert-textbook-html-catalogue-v1",
        inventory_status="complete" if expected <= grades_seen else "partial",
    )
