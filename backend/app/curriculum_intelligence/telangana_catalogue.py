"""Build scoped catalogue snapshots from reviewed Telangana syllabus inventories."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

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
    inventory_kind: str = "detailed_slice",
) -> dict[str, Any]:
    return {
        "pack_code": pack_code,
        "inventory_kind": checked_text(inventory_kind),
        "version_id": version.id,
        "source_revision_id": snapshot.source_revision_id,
        "source_checksum": snapshot.source_checksum,
        "snapshot_id": snapshot.identity,
        "source_completeness_verified": False,
        "synthetic": False,
        "coverage": {
            "status": snapshot.inventory_status,
            "snapshot_row_count": len(snapshot.rows),
            "materialized_metadata_count": coverage.get("materialized_metadata_count", 0),
            "missing_ids": coverage.get("missing_ids", []),
            "unexpected_ids": coverage.get("unexpected_ids", []),
            "duplicate_ids": coverage.get("duplicate_ids", []),
            "conflicting_ids": coverage.get("conflicting_ids", []),
            **{
                key: coverage.get(key, 0)
                for key in (
                    "inventory_observation_count",
                    "resolved_observation_count",
                    "duplicate_observation_count",
                    "unresolved_observation_count",
                    "blocked_observation_count",
                )
            },
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
    """Keep physical coordinates and reject malformed/nested table structures."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict[str, Any]]]] = []
        self._table: list[list[dict[str, Any]]] | None = None
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None
        self._anchor: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._table is not None:
                raise ValueError("Nested SCERT inventory tables require review")
            self._table = []
        elif tag == "tr" and self._table is not None:
            if self._row is not None:
                raise ValueError("Unclosed SCERT inventory row")
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            if self._cell is not None:
                raise ValueError("Unclosed SCERT inventory cell")
            self._cell = {
                "text": [],
                "anchors": [],
                "tag": tag,
                "rowspan": int(attributes.get("rowspan") or "1"),
                "colspan": int(attributes.get("colspan") or "1"),
            }
            if not all(1 <= self._cell[key] <= 100 for key in ("rowspan", "colspan")):
                raise ValueError("Unsupported SCERT inventory span")
        elif tag == "a" and self._cell is not None:
            if self._anchor is not None:
                raise ValueError("Nested SCERT resource anchor")
            self._anchor = {"href": attributes.get("href") or "", "text": []}

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
            if self._anchor is not None:
                raise ValueError("Unclosed SCERT resource anchor")
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._cell is not None:
                raise ValueError("Unclosed SCERT inventory cell")
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._row is not None:
                raise ValueError("Unclosed SCERT inventory row")
            self.tables.append(self._table)
            self._table = None

    def close(self) -> None:
        super().close()
        if any(value is not None for value in (self._table, self._row, self._cell, self._anchor)):
            raise ValueError("Truncated SCERT inventory HTML")


def _table_grid(table: list[list[dict[str, Any]]]) -> list[list[dict[str, Any] | None]]:
    """Expand spans but retain original cell coordinates for exact evidence."""
    occupied: dict[tuple[int, int], dict[str, Any]] = {}
    for row_index, cells in enumerate(table):
        column = 0
        for cell_index, cell in enumerate(cells):
            while (row_index, column) in occupied:
                column += 1
            cell["coordinate"] = f"tr[{row_index + 1}]/cell[{cell_index + 1}]"
            for r in range(row_index, row_index + cell["rowspan"]):
                for c in range(column, column + cell["colspan"]):
                    if (r, c) in occupied or r >= len(table):
                        raise ValueError("Overlapping or truncated SCERT inventory span")
                    occupied[r, c] = cell
            column += cell["colspan"]
    width = max((column + 1 for _, column in occupied), default=0)
    return [[occupied.get((row, column)) for column in range(width)] for row in range(len(table))]


def _catalogue_text(parts: list[str]) -> str:
    value = " ".join(" ".join(parts).replace("\xa0", " ").split())
    return checked_text(value) if value else ""


def _grade_from_text(value: str) -> str | None:
    match = re.fullmatch(r"\s*(10|[1-9])(?:st|nd|rd|th)?\s*", value, re.I)
    return (
        _ROMAN_GRADES.get(match.group(1))
        if match
        else (value.strip().upper() if value.strip().upper() in _ROMAN_GRADES.values() else None)
    )


def _medium_from_text(value: str) -> str | None:
    normalized = value.strip().casefold()
    for medium in (*_SCERT_MEDIA, "Other Media"):
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
    return UNKNOWN


def _language_role(header: str) -> str:
    normalized = header.casefold()
    for ordinal, role in (("first", "first"), ("second", "second"), ("third", "third")):
        if normalized == f"{ordinal} language":
            return role
    non_language_subjects = {
        "maths",
        "mathematics",
        "general science",
        "physical science",
        "biological science",
        "social",
        "social studies",
        "environmental education",
    }
    if normalized in non_language_subjects:
        return "not_applicable"
    return "unknown"


def _book_part(label: str) -> str:
    match = re.search(r"\bpart\s*[- ]?(1|2)\b", label, re.I)
    return f"Part {match.group(1)}" if match else UNKNOWN


def _anchor_label(anchor: dict[str, Any], header: str) -> str:
    label = _catalogue_text(list(anchor.get("text") or []))
    if re.fullmatch(r"part\s*[- ]?[12]", label, re.I):
        return checked_text(f"{header} {label}")
    return label


def scert_textbook_catalogue_snapshot(
    *,
    content: bytes,
    source_url: str,
    pack_id: str,
    version_id: str,
    revision: SourceRevision,
    academic_year: str,
) -> CatalogueSnapshot:
    """Account selected inventory cells without asserting syllabus membership.

    Only an explicit Class/Medium table is supported. Every physical subject
    cell contributes each link, or one missing/unlinked-resource observation.
    Spans retain physical locators; missing cells cannot vanish from coverage.
    """
    try:
        text = checked_text(content.decode("utf-8-sig", errors="strict"))
    except UnicodeError as exc:
        raise ValueError("SCERT catalogue HTML must be valid UTF-8") from exc
    parser = _ScertCatalogueHTMLParser()
    parser.feed(text)
    parser.close()
    rows: list[ScopedCatalogueRow] = []
    observations: list[dict[str, Any]] = []
    identities: dict[str, ScopedCatalogueRow] = {}
    urls: dict[tuple[str, str, str, str], str] = {}
    grades_seen: set[str] = set()
    selected_tables = 0

    def observe(locator: str, status: str, reason: str, identity: str | None = None) -> None:
        observations.append(
            {
                "source_locator": locator,
                "status": status,
                "reason": reason,
                "row_identity": identity,
            }
        )

    for table_index, table in enumerate(parser.tables, 1):
        grid = _table_grid(table)
        header_index = next(
            (
                index
                for index, cells in enumerate(grid)
                if cells
                and all(cell is not None for cell in cells[:2])
                and [_catalogue_text(cell["text"]).casefold() for cell in cells[:2] if cell]
                == ["class", "medium"]
            ),
            None,
        )
        if header_index is None:
            continue
        selected_tables += 1
        headers = [_catalogue_text(cell["text"]) if cell else "" for cell in grid[header_index]]
        if len(headers) < 3 or not all(headers) or len(set(headers)) != len(headers):
            raise ValueError("Ambiguous or missing SCERT subject headers")
        visited: set[str] = set()
        # Even unsupported links before/in the header cannot vanish from a
        # selected table's observed denominator.
        for preheader_cells in table[: header_index + 1]:
            for preheader_cell in preheader_cells:
                for link_index, _ in enumerate(preheader_cell["anchors"], 1):
                    observe(
                        f"table[{table_index}]/{preheader_cell['coordinate']}/a[{link_index}]",
                        "unresolved",
                        "resource outside supported inventory body",
                    )
        for row_index, cells in enumerate(grid[header_index + 1 :], header_index + 2):
            # A rowspan header may occupy multiple rows, but no resource may hide there.
            if all(cell is not None and cell["tag"] == "th" for cell in cells):
                if any(cell["anchors"] for cell in cells if cell):
                    raise ValueError("SCERT header contains unaccounted resources")
                continue
            grade_text = _catalogue_text(cells[0]["text"]) if cells[0] else ""
            medium_text = _catalogue_text(cells[1]["text"]) if cells[1] else ""
            grade = _grade_from_text(grade_text) or UNKNOWN
            medium = _medium_from_text(medium_text) or UNKNOWN
            if grade != UNKNOWN:
                grades_seen.add(grade)
            for column, cell in enumerate(cells):
                prefix = f"table[{table_index}]/"
                locator = prefix + (
                    cell["coordinate"] if cell else f"tr[{row_index}]/missing-cell[{column + 1}]"
                )
                if locator in visited:
                    continue
                visited.add(locator)
                if column < 2:
                    if cell and cell["anchors"]:
                        for link_index, _ in enumerate(cell["anchors"], 1):
                            observe(
                                f"{locator}/a[{link_index}]",
                                "unresolved",
                                "resource in class/medium cell",
                            )
                    continue
                header = headers[column]
                if cell is None:
                    observe(locator, "unresolved", "missing inventory cell")
                    continue
                cell_text = _catalogue_text(cell["text"])
                anchors = cell["anchors"]
                if not anchors:
                    observe(
                        locator,
                        "blocked" if cell_text else "unresolved",
                        "unlinked resource: " + cell_text if cell_text else "empty inventory cell",
                    )
                    continue
                for link_index, anchor in enumerate(anchors, 1):
                    link_locator = f"{locator}/a[{link_index}]"
                    href = checked_text(anchor["href"]) if anchor["href"].strip() else ""
                    label = _anchor_label(anchor, header)
                    resource_url = urljoin(source_url, href)
                    parsed_url = urlsplit(resource_url)
                    if (
                        not href
                        or href.startswith("#")
                        or parsed_url.scheme not in {"http", "https"}
                    ):
                        observe(link_locator, "blocked", "missing or non-resource link")
                        continue
                    if (
                        grade == UNKNOWN
                        or medium == UNKNOWN
                        or not label
                        or cell["colspan"] != 1
                        or cell["rowspan"] != 1
                    ):
                        observe(
                            link_locator, "unresolved", "ambiguous scope, span or missing label"
                        )
                        continue
                    # Parts are link-specific: sibling Part 1/Part 2 must not leak.
                    part = _book_part(label)
                    bilingual = "yes" if "bilingual" in cell_text.casefold() else "unknown"
                    row = ScopedCatalogueRow(
                        pack_id=pack_id,
                        version_id=version_id,
                        source_revision_id=revision.id,
                        source_checksum=revision.checksum,
                        source_locator=link_locator,
                        official_label=label,
                        resource_url=resource_url,
                        grade=grade,
                        academic_year=academic_year,
                        instructional_medium=medium,
                        subject_language=_subject_language(label, header, medium),
                        language_role=_language_role(header),
                        book_part=part,
                        bilingual=bilingual,
                        resource_kind="textbook",
                        document_content_status="not_parsed",
                    )
                    key = (grade, medium, header, resource_url)
                    if key in urls or row.identity in identities:
                        previous = identities[urls.get(key, row.identity)]
                        comparable = {"source_locator"}
                        if row.model_dump(exclude=comparable) == previous.model_dump(
                            exclude=comparable
                        ):
                            observe(
                                link_locator,
                                "duplicate",
                                "repeated resource occurrence",
                                previous.identity,
                            )
                        else:
                            observe(
                                link_locator, "unresolved", "shared URL or conflicting identity"
                            )
                        continue
                    urls[key] = row.identity
                    identities[row.identity] = row
                    rows.append(row)
                    observe(link_locator, "resolved", "linked catalogue metadata", row.identity)
    if not rows:
        raise ValueError("SCERT textbook catalogue contained no usable resource links")
    # A title and a fully accounted rectangular inventory are both required;
    # grade coverage alone is never completeness evidence.
    title_scope = bool(re.search(r"text\s*books?\s+I\s*(?:to|[-–])\s*X", text, re.I))
    explicit_year = academic_year in text or academic_year.replace("-", "–") in text
    complete = (
        selected_tables == 1
        and title_scope
        and explicit_year
        and grades_seen == set(_ROMAN_GRADES.values())
        and all(item["status"] in {"resolved", "duplicate"} for item in observations)
    )
    return CatalogueSnapshot(
        source_revision_id=revision.id,
        source_checksum=revision.checksum,
        rows=tuple(rows),
        extraction_method="scert-textbook-html-catalogue-v2",
        inventory_status="complete" if complete else "partial",
        inventory_observations=tuple(observations),
    )
