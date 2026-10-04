"""Deterministic metadata normalization of already-ingested official HTML indexes.

No network access or bulk document storage lives here. A link proves that an
index lists a resource, not that its PDF was fetched, is current, or contains a
particular syllabus/pattern. Shared grade scopes and placeholder links remain
explicitly unresolved. Public outputs contain short labels/locators only.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote, urljoin, urlsplit

from app.models.enums import SourceRevisionStatus, SourceType
from app.source_intelligence.extractors import normalize_text

if TYPE_CHECKING:
    from app.curriculum_intelligence.service import CurriculumIntelligenceService
    from app.models.source import SourceRevision


class CatalogueExtractionError(ValueError):
    """The supplied source cannot establish a trustworthy index inventory."""


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    line: int
    column: int
    parent: _Element | None = field(default=None, repr=False)
    children: list[_Element | str] = field(default_factory=list)

    def text(self, *, exclude_links: bool = False) -> str:
        return _clean(
            " ".join(
                child if isinstance(child, str) else child.text(exclude_links=exclude_links)
                for child in self.children
                if not (exclude_links and isinstance(child, _Element) and child.tag == "a")
            )
        )

    def ancestors(self) -> list[_Element]:
        result: list[_Element] = []
        parent = self.parent
        while parent is not None:
            result.append(parent)
            parent = parent.parent
        return result


class _IndexParser(HTMLParser):
    _void = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {}, 1, 0)
        self.stack = [self.root]
        self.elements: list[_Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Tolerate the ordinary omitted end tags allowed by HTML tables/lists.
        if tag in {"li", "tr", "td", "th"}:
            siblings = {"td", "th"} if tag in {"td", "th"} else {tag}
            barriers = {"ul", "ol"} if tag == "li" else {"table"}
            for index in range(len(self.stack) - 1, 0, -1):
                if self.stack[index].tag in barriers:
                    break
                if self.stack[index].tag in siblings:
                    self.stack = self.stack[:index]
                    break
        line, column = self.getpos()
        element = _Element(
            tag, {key: value or "" for key, value in attrs}, line, column, self.stack[-1]
        )
        self.stack[-1].children.append(element)
        self.elements.append(element)
        if tag not in self._void:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                return

    def handle_data(self, data: str) -> None:
        if not any(node.tag in {"script", "style", "noscript"} for node in self.stack):
            self.stack[-1].children.append(data)


def _clean(value: str) -> str:
    return " ".join(normalize_text(value).split())


def _parse(content: bytes, source_url: str) -> _IndexParser:
    if urlsplit(source_url).scheme not in {"http", "https"} or not urlsplit(source_url).hostname:
        raise CatalogueExtractionError("An absolute HTTP(S) source URL is required")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogueExtractionError("Index HTML must use the Day-3 UTF-8 contract") from exc
    parser = _IndexParser()
    parser.feed(decoded)
    parser.close()
    if not any(
        element.tag in {"html", "h1", "h2", "h3", "h4", "table", "a"} for element in parser.elements
    ):
        raise CatalogueExtractionError("Source contains no recognizable HTML index")
    return parser


_ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
_GRADE = r"(?:XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I|1[0-2]|[1-9])"
_GRADE_SEQUENCE = rf"({_GRADE})(?:\s*(?:-|–|—|to|and|&|,)\s*({_GRADE}))?"


def _grades(label: str) -> list[str]:
    """Only explicit class/grade labels or parenthesized Roman ranges qualify."""
    match = re.search(rf"\b(?:class(?:es)?|grades?)\s*{_GRADE_SEQUENCE}\b", label, re.I)
    if match is None:
        match = re.search(rf"\(\s*{_GRADE_SEQUENCE}\s*\)", label, re.I)
    if match is None:
        return []
    values = [part.upper() for part in match.groups() if part]
    normalized = list(
        dict.fromkeys(_ROMANS[int(part) - 1] if part.isdigit() else part for part in values)
    )
    if len(normalized) == 2 and re.search(r"[-–—]|\bto\b", match.group(0), re.I):
        first, last = (_ROMANS.index(part) for part in normalized)
        if first <= last:
            return list(_ROMANS[first : last + 1])
    return normalized


def _scope(grades: list[str]) -> str:
    return "explicit_single" if len(grades) == 1 else "shared" if grades else "unresolved"


def _headings(parser: _IndexParser) -> list[_Element]:
    return [element for element in parser.elements if re.fullmatch(r"h[1-6]", element.tag)]


def _descendants(element: _Element, tag: str) -> list[_Element]:
    result: list[_Element] = []
    for child in element.children:
        if isinstance(child, _Element):
            if child.tag == tag:
                result.append(child)
            result.extend(_descendants(child, tag))
    return result


def _index_contexts(parser: _IndexParser) -> dict[int, tuple[str, str, list[str]]]:
    """Honor accordion-target ancestry; fall back to ordinary sequential headings."""
    heading_targets: dict[str, _Element] = {}
    for heading in _headings(parser):
        for anchor in _descendants(heading, "a"):
            href = anchor.attrs.get("href", "")
            if href.startswith("#") and len(href) > 1:
                heading_targets[unquote(href[1:])] = heading
    has_grade_targets = any(_grades(node.text()) for node in heading_targets.values())
    result: dict[int, tuple[str, str, list[str]]] = {}
    section = group = ""
    grades: list[str] = []
    grade_level = 7
    for element in parser.elements:
        if re.fullmatch(r"h[1-6]", element.tag):
            label = element.text()
            candidate_grades = _grades(label)
            if candidate_grades:
                section, group, grades = label, "", candidate_grades
                grade_level = int(element.tag[1])
            elif int(element.tag[1]) <= grade_level:
                section, group, grades = "", "", []
            else:
                group = label
        if element.tag != "a":
            continue
        if has_grade_targets:
            context_headings = [
                heading_targets[node.attrs["id"]]
                for node in reversed(element.ancestors())
                if node.attrs.get("id") in heading_targets
            ]
            section, group, grades = "", "", []
            for heading in context_headings:
                candidate_grades = _grades(heading.text())
                if candidate_grades:
                    section, grades = heading.text(), candidate_grades
                else:
                    group = heading.text()
        result[id(element)] = (section, group, list(grades))
    return result


def _link(anchor: _Element, source_url: str) -> dict[str, Any]:
    href = anchor.attrs.get("href", "").strip()
    url = urljoin(source_url, href)
    parsed = urlsplit(url)
    same_origin = (parsed.hostname or "").casefold() == (
        urlsplit(source_url).hostname or ""
    ).casefold()
    is_pdf = unquote(parsed.path).casefold().endswith(".pdf")
    placeholder = bool(
        re.fullmatch(
            r"(?:error|not[_-]?available|coming[_-]?soon|placeholder)\.pdf",
            parsed.path.rsplit("/", 1)[-1],
            re.I,
        )
    )
    reasons = []
    if parsed.scheme not in {"https", "http"} or not same_origin or parsed.username:
        reasons.append("link_requires_authority_review")
    if parsed.scheme == "http" and urlsplit(source_url).scheme == "https":
        reasons.append("link_uses_insecure_http")
    if not is_pdf:
        reasons.append("not_a_document_pdf_link")
    if placeholder:
        reasons.append("placeholder_document_link")
    anchor_id = anchor.attrs.get("id") or next(
        (node.attrs["id"] for node in anchor.ancestors() if node.attrs.get("id")), None
    )
    return {
        "label": anchor.text(),
        "href": href,
        "url": url,
        "anchor_id": anchor_id,
        "source_locator": f"HTML line {anchor.line}, column {anchor.column + 1}",
        "same_authority_host": same_origin,
        "is_pdf": is_pdf,
        "availability": "unresolved" if reasons else "linked_unverified",
        "document_content_verified": False,
        "review_required": bool(reasons),
        "unresolved_reasons": reasons,
    }


def _subject_code(label: str) -> str | None:
    # An explicit index label may expose a code. Never derive it from a filename.
    match = re.search(r"\b(?:subject\s+)?code\s*[:=-]?\s*(\d{3})\b|\((\d{3})\)\s*$", label, re.I)
    return next((group for group in match.groups() if group), None) if match else None


def _key(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:24]


def _academic_year(value: str) -> str | None:
    match = re.search(r"\b(20\d{2})\s*[-–—]\s*((?:20)?\d{2})\b", value)
    return f"{match.group(1)}-{match.group(2)[-2:]}" if match else None


def _year(parser: _IndexParser) -> str | None:
    years = {
        year
        for heading in _headings(parser)
        if (year := _academic_year(heading.text())) is not None
    }
    return next(iter(years)) if len(years) == 1 else None


def parse_curriculum_index(content: bytes, *, source_url: str) -> dict[str, Any]:
    """Extract all PDF anchors; infer no PDF contents or fine-grained grade scope.

    ``subjects`` are subject-index entries, ``resources`` retain every PDF link,
    and ``by_grade`` is a candidate grouping, not a claim of verified PDF scope.
    ``label`` always preserves the anchor wording; ``subject_label`` may join an
    explicit list prefix such as Urdu with the Course A anchor.
    """
    parser = _parse(content, source_url)
    contexts = _index_contexts(parser)
    resources: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for anchor in parser.elements:
        if anchor.tag != "a" or any(
            node.tag in {"script", "style", "noscript"} for node in anchor.ancestors()
        ):
            continue
        link = _link(anchor, source_url)
        if not link["is_pdf"]:
            continue
        section, group, grades = contexts[id(anchor)]
        label = link["label"]
        container = next((node for node in anchor.ancestors() if node.tag == "li"), None)
        prefix = container.text(exclude_links=True) if container else ""
        role = "subject_syllabus"
        if re.search(r"initial pages", group, re.I) or re.search(
            r"introduction to .*curriculum", label, re.I
        ):
            role = "introductory_material"
        elif re.search(
            r"reading material|supplementary material|additional resources", label, re.I
        ):
            role = "supplementary_material"
        if not grades and role == "subject_syllabus":
            role = "unclassified_document"
        subject_label = _clean(f"{prefix} {label}") if prefix else label
        if role == "supplementary_material" and container:
            other = next(
                (
                    item.text()
                    for item in _descendants(container, "a")
                    if item is not anchor
                    and not re.search(
                        r"reading material|supplementary material|additional resources",
                        item.text(),
                        re.I,
                    )
                ),
                "",
            )
            subject_label = prefix or other or label
        reasons = list(link["unresolved_reasons"])
        if len(grades) != 1:
            reasons.append(
                "shared_grade_scope_requires_document_review"
                if grades
                else "grade_scope_unresolved"
            )
        if not label:
            reasons.append("subject_label_unresolved")
        stable_key = _key(source_url, section, group, subject_label, label, link["url"])
        locator = " > ".join(
            part for part in (section, group, subject_label, link["source_locator"]) if part
        )
        if stable_key in seen:
            seen[stable_key]["source_locators"].append(locator)
            continue
        entry = {
            **link,
            "key": stable_key,
            "subject_label": subject_label,
            "official_subject_code": _subject_code(subject_label),
            "section": section,
            "group": group,
            "grade_candidates": grades,
            "grade_scope": _scope(grades),
            "resource_type": role,
            "source_locator": locator,
            "source_locators": [locator],
            "review_required": bool(reasons),
            "unresolved_reasons": reasons,
            "syllabus_content_status": "not_parsed",
        }
        seen[stable_key] = entry
        resources.append(entry)
    subjects = [entry for entry in resources if entry["resource_type"] == "subject_syllabus"]
    by_grade: dict[str, list[dict[str, Any]]] = {}
    for entry in subjects:
        for grade in entry["grade_candidates"]:
            by_grade.setdefault(grade, []).append(entry)
    return {
        "kind": "curriculum",
        "source_url": source_url,
        "academic_year": _year(parser),
        "resources": resources,
        "subjects": subjects,
        "by_grade": by_grade,
        "unresolved": [entry for entry in resources if entry["review_required"]],
        "index_subject_count": len(subjects),
        "resource_count": len(resources),
        "complete_curriculum": False,
        "content_coverage": "index_metadata_only",
    }


def _assessment_kind(label: str) -> str | None:
    label = label.casefold().strip()
    if label == "sqp" or "sample question paper" in label:
        return "sample_question_paper"
    if label == "ms" or "marking scheme" in label:
        return "marking_scheme"
    return None


def parse_assessment_index(content: bytes, *, source_url: str) -> dict[str, Any]:
    """Separate each subject's SQP/MS links; sections and marks stay unresolved."""
    parser = _parse(content, source_url)
    heading_grades = {
        _grades(heading.text())[0]
        for heading in _headings(parser)
        if len(_grades(heading.text())) == 1
    }
    grades = sorted(heading_grades, key=_ROMANS.index)
    entries: list[dict[str, Any]] = []
    for table in [element for element in parser.elements if element.tag == "table"]:
        headers: dict[int, str] = {}
        for row in _descendants(table, "tr"):
            if next((node for node in row.ancestors() if node.tag == "table"), None) is not table:
                continue
            cells = [
                child
                for child in row.children
                if isinstance(child, _Element) and child.tag in {"td", "th"}
            ]
            if not cells:
                continue
            if cells[0].text().casefold() in {"subject", "subjects", "subject name"}:
                headers = {
                    index: kind
                    for index, cell in enumerate(cells)
                    if (kind := _assessment_kind(cell.text()))
                }
                continue
            # Layout tables surrounding the real subject table are not data rows.
            if not headers:
                continue
            subject = cells[0].text()
            if not subject or len(cells) < 2:
                continue
            documents: list[dict[str, Any]] = []
            for index, cell in enumerate(cells[1:], start=1):
                for anchor in _descendants(cell, "a"):
                    link = _link(anchor, source_url)
                    label_kind = _assessment_kind(link["label"])
                    kind = label_kind or headers.get(index)
                    reasons = list(link["unresolved_reasons"])
                    if kind is None:
                        reasons.append("assessment_document_kind_unresolved")
                    elif label_kind and headers.get(index) not in {None, label_kind}:
                        reasons.append("assessment_document_kind_conflict")
                    # A correctly captioned link to the opposite file is not proof.
                    filename_kind = re.search(
                        r"[-_](SQP|MS)\.pdf$", urlsplit(link["url"]).path, re.I
                    )
                    if filename_kind and _assessment_kind(filename_kind.group(1)) != kind:
                        reasons.append("assessment_filename_kind_conflict")
                    documents.append(
                        {
                            **link,
                            "document_type": kind or "unresolved",
                            "review_required": bool(reasons),
                            "availability": "unresolved" if reasons else "linked_unverified",
                            "unresolved_reasons": reasons,
                        }
                    )
            if not documents:
                continue
            sqps = [doc for doc in documents if doc["document_type"] == "sample_question_paper"]
            schemes = [doc for doc in documents if doc["document_type"] == "marking_scheme"]
            shared_urls = {doc["url"] for doc in sqps} & {doc["url"] for doc in schemes}
            if shared_urls:
                for document in documents:
                    if document["url"] in shared_urls:
                        document["unresolved_reasons"].append("sqp_and_ms_share_document_url")
                        document.update(review_required=True, availability="unresolved")
            reasons = []
            if len(grades) != 1:
                reasons.append("grade_scope_unresolved")
            if not sqps or not schemes:
                reasons.append("assessment_document_pair_incomplete")
            if any(doc["review_required"] for doc in documents):
                reasons.append("assessment_links_require_review")
            entries.append(
                {
                    "key": _key(source_url, subject, ",".join(grades)),
                    "subject_label": subject,
                    "official_subject_code": _subject_code(subject),
                    "grade_candidates": grades,
                    "grade_scope": _scope(grades),
                    "source_locator": (f"HTML table > {subject} > row at line {row.line}"),
                    "documents": documents,
                    "sample_question_papers": sqps,
                    "marking_schemes": schemes,
                    "sample_question_paper_linked": any(
                        doc["availability"] == "linked_unverified" for doc in sqps
                    ),
                    "marking_scheme_linked": any(
                        doc["availability"] == "linked_unverified" for doc in schemes
                    ),
                    "pattern_details": {
                        "status": "unresolved",
                        "sections": None,
                        "total_marks": None,
                        "question_categories": None,
                        "competency_emphasis": None,
                    },
                    "curriculum_membership_effect": "none",
                    "review_required": bool(reasons),
                    "unresolved_reasons": reasons,
                }
            )
    return {
        "kind": "assessment",
        "source_url": source_url,
        "academic_year": _year(parser),
        "subjects": entries,
        "subject_count": len(entries),
        "unresolved": [entry for entry in entries if entry["review_required"]],
        "curriculum_membership_effect": "none",
        "content_coverage": "index_metadata_only",
    }


def extract_stored_index(
    service: CurriculumIntelligenceService,
    revision: SourceRevision,
    *,
    kind: Literal["curriculum", "assessment"],
) -> dict[str, Any]:
    """Normalize a validated active Day-3 revision, with its exact provenance.

    Fail closed rather than parsing manual registry metadata, stale extraction,
    staged bytes, a different source domain, or a tampered storage object.
    """
    if kind not in {"curriculum", "assessment"}:
        raise CatalogueExtractionError("Unknown index kind")
    if revision.status != SourceRevisionStatus.ACTIVE.value:
        raise CatalogueExtractionError("Index normalization requires an active source revision")
    if not service.has_source_content(revision) or not revision.storage_path:
        raise CatalogueExtractionError("Original extracted source bytes are unavailable")
    expected_types = (
        {SourceType.OFFICIAL_SYLLABUS.value}
        if kind == "curriculum"
        else {SourceType.SAMPLE_PAPER.value, SourceType.MARKING_SCHEME.value}
    )
    if revision.source.source_type not in expected_types:
        raise CatalogueExtractionError("Source type does not match the index domain")
    if (revision.content_type or "").split(";", 1)[0].strip().lower() not in {
        "text/html",
        "application/xhtml+xml",
    }:
        raise CatalogueExtractionError("Index normalization requires original HTML")
    source_url = revision.source.url
    if not source_url:
        raise CatalogueExtractionError("Index source URL is unavailable")
    content = service.source_service.storage.read(revision.storage_path)
    if hashlib.sha256(content).hexdigest() != revision.checksum:
        raise CatalogueExtractionError("Stored source checksum mismatch")
    parser = parse_curriculum_index if kind == "curriculum" else parse_assessment_index
    report = parser(content, source_url=source_url)
    if not report["subjects"]:
        raise CatalogueExtractionError("Index contains no identifiable subject records")
    expected_year = _academic_year(revision.source.academic_year or "")
    if expected_year and expected_year != report["academic_year"]:
        raise CatalogueExtractionError("Index academic year is missing or mismatches its source")
    expected_grades = revision.source.metadata_json.get("grade_codes")
    if kind == "assessment" and expected_grades:
        observed_grades = {
            grade for entry in report["subjects"] for grade in entry["grade_candidates"]
        }
        if observed_grades != set(expected_grades):
            raise CatalogueExtractionError("Assessment index grade mismatches its source scope")
    report.update(
        source_revision_id=revision.id, checksum=revision.checksum, extraction_verified=True
    )
    for entry in report["resources"] if kind == "curriculum" else report["subjects"]:
        entry.update(
            source_revision_id=revision.id, source_url=source_url, source_checksum=revision.checksum
        )
    return report
