"""Synthetic structure-only fixtures; no bulk official documents are committed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.curriculum_intelligence.catalogue import (
    CatalogueExtractionError,
    extract_stored_index,
    parse_assessment_index,
    parse_curriculum_index,
)
from app.curriculum_intelligence.service import CurriculumIntelligenceService, load_source_manifest
from app.day4_verify import SOURCE_MANIFEST
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.enums import SourceRevisionStatus
from app.source_intelligence.security import FetchedSource, SourceUrlFetcher
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

URL = "https://cbseacademic.nic.in/curriculum_2027.html"
SQP_URL = "https://cbseacademic.nic.in/SQP_CLASSX_2026-27.html"

# Short synthetic subset of the inspected accordion/list structure. Labels and
# link shapes are illustrative, not an assertion that these bytes are official.
CURRICULUM = b"""<html><body>
<h2>Curriculum for the Academic Year 2026-27</h2>
<h4><a href="#grade9">Secondary Curriculum: Part - 1 (Class IX)</a></h4>
<div id="grade9">
<h4><a href="#intro9">Initial Pages</a></h4><div id="intro9">
<a href="intro.pdf">Introduction to Secondary Curriculum</a></div>
<h4><a href="#main9">Main Subjects</a></h4><div id="main9"><ul>
<li><a href="math9.pdf">Mathematics</a></li>
<li><a href="advanced9.pdf">Mathematics at Advanced Level</a></li>
<li><a href="science9.pdf">Science</a><br><a href="reading9.pdf">Reading Material</a></li>
</ul></div></div>
<h4><a href="#grade10">Secondary Curriculum: Part - 1 (Class X)</a></h4>
<div id="grade10"><h4><a href="#languages10">Languages - (Group-L)</a></h4>
<div id="languages10"><ul><li>Urdu<br><br><a href="urdua.pdf">Course A</a><br>
<a href="urdub.pdf">Course B</a></li><li><a href="shared.pdf">Arabic</a></li></ul></div></div>
<h4><a href="#senior">Secondary Curriculum: Part - 2 (XI-XII)</a></h4>
<div id="senior"><h4><a href="#electives">Academic Electives - (Group-A)</a></h4>
<div id="electives"><ul><li><a href="maths.pdf">Mathematics</a></li>
<li><a href="computer.pdf">Computer Science</a></li>
<li><a href="shared.pdf">Arabic</a></li></ul></div></div>
<a href="orphan.pdf">Unclassified resource</a>
<!-- <a href="comment.pdf">Never extracted</a> -->
<script>var text = '<a href="fake.pdf">Fake</a>';</script>
</body></html>"""

ASSESSMENT = b"""<html><h3>Class X Sample Question Paper &amp; Marking Scheme for Exam 2026-27</h3>
<table><tr><td>Layout sidebar</td><td><table id="circulars">
<tr><th>Subject</th><th>Sample Question Paper</th><th>Marking Scheme</th></tr>
<tr><td><b>Mathematics (Standard)</b></td><td><a href="MathsStandard-SQP.pdf">SQP</a></td>
<td><a href="MathsStandard-MS.pdf">MS</a></td></tr>
<tr><td>Bengali</td><td><a href="error.pdf">SQP</a></td>
<td><a href="error.pdf">MS</a></td></tr>
<tr><td>Science</td><td><a href="Science-SQP.pdf">SQP</a></td><td>Coming soon</td></tr>
</table></td></tr></table></html>"""


def test_all_curriculum_subjects_and_exact_source_anchors_are_preserved() -> None:
    report = parse_curriculum_index(CURRICULUM, source_url=URL)
    assert report["index_subject_count"] == 9
    assert report["resource_count"] == 12
    assert report["academic_year"] == "2026-27"
    assert set(report["by_grade"]) == {"IX", "X", "XI", "XII"}
    assert len(report["by_grade"]["IX"]) == 3
    subject = report["by_grade"]["IX"][0]
    assert subject["label"] == "Mathematics"
    assert subject["href"] == "math9.pdf"
    assert subject["url"] == "https://cbseacademic.nic.in/math9.pdf"
    assert subject["anchor_id"] == "main9"
    assert "Class IX" in subject["source_locator"]
    assert "Main Subjects" in subject["source_locator"]
    assert "HTML line" in subject["source_locator"]
    assert subject["review_required"] is False
    assert subject["document_content_verified"] is False
    assert subject["syllabus_content_status"] == "not_parsed"
    assert report["complete_curriculum"] is False


def test_shared_grades_and_unscoped_links_are_not_invented() -> None:
    report = parse_curriculum_index(CURRICULUM, source_url=URL)
    shared = report["by_grade"]["XI"][0]
    assert shared["grade_candidates"] == ["XI", "XII"]
    assert shared["grade_scope"] == "shared"
    assert shared["review_required"] is True
    orphan = next(item for item in report["resources"] if item["href"] == "orphan.pdf")
    assert orphan["grade_candidates"] == []
    assert orphan["grade_scope"] == "unresolved"
    assert orphan["review_required"] is True
    # An identical PDF listed in two scopes must retain both occurrences.
    assert len([item for item in report["subjects"] if item["href"] == "shared.pdf"]) == 2


def test_course_prefix_and_supplements_do_not_create_invented_subjects() -> None:
    report = parse_curriculum_index(CURRICULUM, source_url=URL)
    subjects = {item["subject_label"]: item for item in report["subjects"]}
    assert subjects["Urdu Course A"]["label"] == "Course A"
    assert subjects["Urdu Course B"]["label"] == "Course B"
    assert "Reading Material" not in subjects
    supplement = next(item for item in report["resources"] if item["href"] == "reading9.pdf")
    assert supplement["subject_label"] == "Science"
    assert supplement["resource_type"] == "supplementary_material"
    assert all(item["href"] not in {"fake.pdf", "comment.pdf"} for item in report["resources"])


def test_catalogue_keys_are_deterministic_and_not_based_on_line_numbers() -> None:
    first = parse_curriculum_index(CURRICULUM, source_url=URL)
    second = parse_curriculum_index(b"\n\n" + CURRICULUM, source_url=URL)
    assert [item["key"] for item in first["resources"]] == [
        item["key"] for item in second["resources"]
    ]
    assert first["resources"][0]["source_locator"] != second["resources"][0]["source_locator"]


def test_duplicate_anchors_preserve_locators_without_duplicate_subjects() -> None:
    html = b'<h2>Class IX</h2><a href="x.pdf">Subject</a>\n<a href="x.pdf">Subject</a>'
    report = parse_curriculum_index(html, source_url=URL)
    assert report["index_subject_count"] == 1
    assert len(report["subjects"][0]["source_locators"]) == 2


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("Class 9", ["IX"]),
        ("Classes IX-XII", ["IX", "X", "XI", "XII"]),
        ("Grade XI and XII", ["XI", "XII"]),
        ("Secondary (XI-XII)", ["XI", "XII"]),
        ("2026-27", []),
        ("No class indicated", []),
    ],
)
def test_grade_scope_comes_from_explicit_headings(heading: str, expected: list[str]) -> None:
    report = parse_curriculum_index(
        f'<h2>{heading}</h2><h3>Subjects</h3><a href="x.pdf">Subject</a>'.encode(),
        source_url=URL,
    )
    assert report["resources"][0]["grade_candidates"] == expected


def test_external_authority_and_insecure_links_stay_review_required() -> None:
    html = b"""<h2>Class X</h2>
    <base href="https://untrusted.example/">
    <a href="normal.pdf">Safe relative link</a>
    <a href="https://untrusted.example/other.pdf">External</a>
    <a href="http://cbseacademic.nic.in/old.pdf">Insecure</a>"""
    result = parse_curriculum_index(html, source_url=URL)
    assert result["subjects"][0]["url"] == "https://cbseacademic.nic.in/normal.pdf"
    assert result["subjects"][0]["review_required"] is False
    assert all(item["review_required"] for item in result["subjects"][1:])


def test_assessment_links_are_separate_structured_evidence_not_syllabus_rules() -> None:
    report = parse_assessment_index(ASSESSMENT, source_url=SQP_URL)
    assert report["subject_count"] == 3  # Outer layout tables must not duplicate rows.
    assert report["academic_year"] == "2026-27"
    math = report["subjects"][0]
    assert math["subject_label"] == "Mathematics (Standard)"
    assert math["grade_candidates"] == ["X"]
    assert math["sample_question_paper_linked"] is True
    assert math["marking_scheme_linked"] is True
    assert math["sample_question_papers"][0]["url"].endswith("MathsStandard-SQP.pdf")
    assert math["marking_schemes"][0]["url"].endswith("MathsStandard-MS.pdf")
    assert math["pattern_details"] == {
        "status": "unresolved",
        "sections": None,
        "total_marks": None,
        "question_categories": None,
        "competency_emphasis": None,
    }
    assert report["curriculum_membership_effect"] == math["curriculum_membership_effect"] == "none"


def test_error_pdf_and_missing_marking_scheme_never_claim_published_documents() -> None:
    report = parse_assessment_index(ASSESSMENT, source_url=SQP_URL)
    bengali, science = report["subjects"][1:]
    assert bengali["sample_question_paper_linked"] is False
    assert bengali["marking_scheme_linked"] is False
    assert bengali["review_required"] is True
    assert "placeholder_document_link" in bengali["documents"][0]["unresolved_reasons"]
    assert science["marking_schemes"] == []
    assert science["marking_scheme_linked"] is False
    assert science["review_required"] is True


def test_assessment_rejects_conflicting_kind_and_grade_scope() -> None:
    html = ASSESSMENT.replace(b"Class X Sample", b"Class XII Sample")
    html = html.replace(b'MathsStandard-MS.pdf">MS', b'MathsStandard-SQP.pdf">MS')
    report = parse_assessment_index(html, source_url=SQP_URL)
    assert report["subjects"][0]["grade_candidates"] == ["XII"]  # Never guess from URL.
    assert report["subjects"][0]["marking_scheme_linked"] is False
    ambiguous = parse_assessment_index(b"<h3>Class X</h3>" + html, source_url=SQP_URL)
    assert ambiguous["subjects"][0]["review_required"] is True
    assert ambiguous["subjects"][0]["grade_scope"] == "shared"


class _SyntheticHtmlFetcher(SourceUrlFetcher):
    def __init__(self, content: bytes) -> None:
        self.content = content

    def fetch(self, url: str) -> FetchedSource:
        return FetchedSource(self.content, url, "text/html", "synthetic-index.html")


@pytest.fixture
def catalogue_service(tmp_path: Path) -> Iterator[CurriculumIntelligenceService]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'catalogue.db'}")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    source_service = SourceIntelligenceService(
        session,
        storage=LocalSourceStorage(tmp_path / "private"),
        fetcher=_SyntheticHtmlFetcher(CURRICULUM),
    )
    try:
        yield CurriculumIntelligenceService(session, source_service=source_service)
    finally:
        session.close()
        engine.dispose()
        create_database_engine.cache_clear()


def _revisions(service: CurriculumIntelligenceService, *, fetch: bool = True) -> dict[str, Any]:
    entries = [
        item
        for item in load_source_manifest(SOURCE_MANIFEST)
        if item.key == "cbse-curriculum-2026-27"
    ]
    return service.ensure_manifest_sources(entries, actor_id="synthetic-test", fetch_content=fetch)


def test_stored_extraction_reuses_day3_bytes_and_exact_revision(
    catalogue_service: CurriculumIntelligenceService,
) -> None:
    revision = _revisions(catalogue_service)["cbse-curriculum-2026-27"]
    report = extract_stored_index(catalogue_service, revision, kind="curriculum")
    assert report["extraction_verified"] is True
    assert report["source_revision_id"] == revision.id
    assert report["checksum"] == revision.checksum
    assert report["subjects"][0]["source_revision_id"] == revision.id
    assert report["subjects"][0]["source_checksum"] == revision.checksum
    assert extract_stored_index(catalogue_service, revision, kind="curriculum") == report


def test_registry_metadata_cannot_masquerade_as_an_extracted_catalogue(
    catalogue_service: CurriculumIntelligenceService,
) -> None:
    revision = _revisions(catalogue_service, fetch=False)["cbse-curriculum-2026-27"]
    with pytest.raises(CatalogueExtractionError, match="bytes are unavailable"):
        extract_stored_index(catalogue_service, revision, kind="curriculum")


def test_staged_tampered_and_wrong_domain_indexes_are_rejected(
    catalogue_service: CurriculumIntelligenceService,
) -> None:
    revision = _revisions(catalogue_service)["cbse-curriculum-2026-27"]
    with pytest.raises(CatalogueExtractionError, match="index domain"):
        extract_stored_index(catalogue_service, revision, kind="assessment")
    revision.status = SourceRevisionStatus.STAGED.value
    with pytest.raises(CatalogueExtractionError, match="active source revision"):
        extract_stored_index(catalogue_service, revision, kind="curriculum")
    revision.status = SourceRevisionStatus.ACTIVE.value
    assert revision.storage_path
    (catalogue_service.source_service.storage.root / revision.storage_path).write_bytes(b"tampered")
    with pytest.raises(CatalogueExtractionError, match="checksum mismatch"):
        extract_stored_index(catalogue_service, revision, kind="curriculum")


@pytest.mark.parametrize("content", [b"\xff", b"not an HTML index"])
def test_invalid_html_is_not_silently_normalized(content: bytes) -> None:
    with pytest.raises(CatalogueExtractionError):
        parse_curriculum_index(content, source_url=URL)


def test_introduction_named_subjects_are_not_mistaken_for_front_matter() -> None:
    html = b"""<h2>Class IX</h2><h3>Optional Subjects</h3>
    <a href="405-FMM-IX.pdf">Introduction to Financial Markets</a>
    <a href="406-TOURISM-IX.pdf">Introduction to Tourism</a>
    <a href="math.pdf">Mathematics (041)</a>"""
    report = parse_curriculum_index(html, source_url=URL)
    assert report["index_subject_count"] == 3
    assert report["subjects"][0]["official_subject_code"] is None
    assert report["subjects"][2]["official_subject_code"] == "041"


def test_stored_index_rejects_wrong_academic_year(
    catalogue_service: CurriculumIntelligenceService,
) -> None:
    catalogue_service.source_service.fetcher = _SyntheticHtmlFetcher(
        CURRICULUM.replace(b"2026-27", b"2025-26")
    )
    revision = _revisions(catalogue_service)["cbse-curriculum-2026-27"]
    with pytest.raises(CatalogueExtractionError, match="academic year"):
        extract_stored_index(catalogue_service, revision, kind="curriculum")


def test_full_year_heading_is_normalized_to_academic_year_code() -> None:
    report = parse_curriculum_index(CURRICULUM.replace(b"2026-27", b"2026-2027"), source_url=URL)
    assert report["academic_year"] == "2026-27"
