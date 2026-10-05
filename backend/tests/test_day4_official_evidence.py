from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.orm import Session

from app.curriculum_intelligence.evidence import EvidenceAnchor, check_evidence_anchors
from app.curriculum_intelligence.official_demo import OUTCOME_TEXT, official_source_demonstration
from app.curriculum_intelligence.service import CurriculumIntelligenceService, load_source_manifest
from app.day4_verify import SOURCE_MANIFEST
from app.db.base import Base
from app.db.session import create_database_engine
from app.source_intelligence.security import FetchedSource, SourceUrlFetcher
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def _pdf(pages: list[str]) -> bytes:
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(612, 792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        lines = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in text.split("\n")
        ]
        stream.set_data(
            (
                "BT /F1 9 Tf 20 700 Td 12 TL "
                + " T* ".join(f"({line}) Tj" for line in lines)
                + " ET"
            ).encode()
        )
        page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class SyntheticEvidenceFetcher(SourceUrlFetcher):
    """Synthetic transport for contract tests; never used in live verification."""

    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents

    def fetch(self, url: str) -> FetchedSource:
        content = self.contents[url]
        is_html = content.startswith(b"<")
        return FetchedSource(
            content,
            url,
            "text/html" if is_html else "application/pdf",
            "synthetic.html" if is_html else "synthetic.pdf",
        )


@pytest.fixture
def evidence_service(tmp_path: Path) -> Any:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'evidence.db'}")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    source_service = SourceIntelligenceService(
        session, storage=LocalSourceStorage(tmp_path / "private")
    )
    service = CurriculumIntelligenceService(session, source_service=source_service)
    try:
        yield service
    finally:
        session.close()
        engine.dispose()
        create_database_engine.cache_clear()


def _official_test_revisions(
    service: CurriculumIntelligenceService,
    *,
    outcome_page: str = OUTCOME_TEXT,
    adjacent_page: str = "Relevant CGs: CG-3, C-3.2",
) -> dict[str, Any]:
    pages = ["Synthetic page"] * 57
    pages[45] = "Mathematics CG-3 C-3.2"
    pages[55] = "13. Linear Equations in Two Variables\n" + outcome_page
    pages[56] = adjacent_page + "\n14. Mensuration"
    contents = {
        "ncfse-2023-ncert-official": _pdf(["National Curriculum Framework 2023"]),
        "ncert-grade-9-phase-i-part-2-draft": _pdf(pages),
        "cbse-mathematics-class-ix-2026-27": _pdf(["Linear Equations in Two Variables C-3.2"]),
        "cbse-curriculum-2026-27": _pdf(["Mathematics 2026-27"]),
        "cbse-class-x-sqp-2026-27": _pdf(["Mathematics Standard SQP MS"]),
    }
    for key, code, total, questions, summaries, syllabus_key, headings in [
        (
            "maths-x",
            "041",
            80,
            38,
            [(20, 1), (5, 2), (6, 3), (4, 5), (3, 4)],
            "cbse-mathematics-class-x-2026-27",
            "Number Systems Real Numbers",
        ),
        (
            "physics-xii",
            "042",
            70,
            33,
            [(16, 1), (5, 2), (7, 3), (2, 4), (3, 5)],
            "cbse-physics-xi-xii-2026-27",
            "Electrostatics Electric Charges and Fields",
        ),
    ]:
        contents[syllabus_key] = _pdf([headings])
        header = (
            f"{code} Maximum Marks: {total} Time Allowed: 3 hours. Contains {questions} questions. "
        )
        section_text = " ".join(
            f"SECTION {chr(65 + i)} ({count} x {marks} = {count * marks})"
            for i, (count, marks) in enumerate(summaries)
        )
        kinds = [
            "multiple choice",
            "very short answer",
            "short answer",
            "long answer",
            "case study",
        ]
        if key == "physics-xii":
            kinds = ["multiple choice", "", "", "case study", "long answer"]
        instructions = []
        for i, ((count, marks), kind) in enumerate(zip(summaries, kinds, strict=True)):
            if i == 0:
                mcq_count = 18 if key == "maths-x" else 12
                instructions.append(
                    f"Section A contains {count} questions, {mcq_count} MCQ and "
                    f"{count - mcq_count} Assertion-Reasoning based of {marks} mark each. "
                )
            else:
                instructions.append(
                    f"Section {chr(65 + i)} contains {count} {kind} questions "
                    f"of {marks} marks each. "
                )
        contents[f"cbse-{key}-sqp-2026-27"] = _pdf([header + "".join(instructions) + section_text])
        contents[f"cbse-{key}-ms-2026-27"] = _pdf([f"{code} 2026 Marking Scheme"])
    from test_day4_catalogue import ASSESSMENT, CURRICULUM

    contents["cbse-curriculum-2026-27"] = CURRICULUM
    contents["cbse-class-x-sqp-2026-27"] = ASSESSMENT
    contents["cbse-class-xii-sqp-2026-27"] = ASSESSMENT.replace(b"Class X ", b"Class XII ").replace(
        b"Mathematics (Standard)", b"Physics"
    )
    entries = [entry for entry in load_source_manifest(SOURCE_MANIFEST) if entry.key in contents]
    service.source_service.fetcher = SyntheticEvidenceFetcher(
        {entry.url: contents[entry.key] for entry in entries}
    )
    return service.ensure_manifest_sources(entries, actor_id="synthetic-test", fetch_content=True)


def test_source_backed_path_requires_verified_bytes_and_exact_pages(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    revisions = _official_test_revisions(evidence_service)
    first = official_source_demonstration(evidence_service, revisions)
    second = official_source_demonstration(evidence_service, revisions)
    assert first["verified"] is True
    assert first["status"] == "initial_scope_verified_with_source_reviews"
    assert first["acceptance"]["passed"] is True
    assert first["catalogue_inventory"]["coverage_denominator"]["detailed_syllabus_paths"] == 3
    assert first["publication_status"]["ncert_grade_9"] == "draft"
    assert first["alignment_status"] == "partial"
    assert first["complete_catalogue"] is False
    assert len(first["path"]["node_ids"]) == 7
    assert first["path"] == second["path"]
    assert len(first["path"]["learning_outcome_ids"]) == 1
    assert len(first["path"]["competency_ids"]) == 1
    assert len(first["framework_structure"]["nodes"]) == 4
    assert first["framework_structure"]["learning_outcome_links"][0]["status"] == "direct"
    assert all(item["assessment_status"] == "verified" for item in first["initial_baselines"])
    assert {item["assessment_pattern"]["total_marks"] for item in first["initial_baselines"]} == {
        70,
        80,
    }


def test_page_or_checksum_mismatch_cannot_pass_official_gate(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    revisions = _official_test_revisions(evidence_service)
    anchor = EvidenceAnchor(
        "wrong-page", "ncert-grade-9-phase-i-part-2-draft", (OUTCOME_TEXT,), page=55
    )
    assert check_evidence_anchors(evidence_service, revisions, [anchor])["verified"] is False
    revision = revisions["ncfse-2023-ncert-official"]
    revision.checksum = "f" * 64
    revision.extracted_checksum = revision.checksum
    report = official_source_demonstration(evidence_service, revisions)
    assert report["verified"] is False
    assert report["checks"][0]["reason"] == "stored source checksum mismatch"


def test_missing_or_registry_source_cannot_pass_official_gate(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    report = official_source_demonstration(evidence_service, {})
    assert report["verified"] is False
    assert "path" not in report
    entry = load_source_manifest(SOURCE_MANIFEST)[0]
    registry = evidence_service.ensure_manifest_sources([entry], actor_id="test")
    assert (
        check_evidence_anchors(
            evidence_service, registry, [EvidenceAnchor("registry", entry.key, ("anything",))]
        )["verified"]
        is False
    )


def test_official_verifier_can_opt_in_to_bounded_larger_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings

    monkeypatch.delenv("SOURCE_MAX_BYTES", raising=False)
    assert Settings(_env_file=None).source_max_bytes == 25 * 1024 * 1024
    monkeypatch.setenv("SOURCE_MAX_BYTES", str(64 * 1024 * 1024))
    assert Settings(_env_file=None).source_max_bytes == 64 * 1024 * 1024


@pytest.mark.parametrize(
    "missing", ["catalogue", "framework", "maths_pattern", "physics_path", "sqp_index"]
)
def test_aggregate_gate_rejects_missing_required_constituents(
    evidence_service: CurriculumIntelligenceService,
    missing: str,
) -> None:
    from app.curriculum_intelligence.acceptance import evaluate_day4_acceptance

    revisions = _official_test_revisions(evidence_service)
    report = official_source_demonstration(evidence_service, revisions)
    assert report["acceptance"]["passed"]
    if missing == "catalogue":
        report["catalogue_inventory"]["extraction_verified"] = False
    elif missing == "framework":
        report["framework_structure"]["learning_outcome_links"] = []
    elif missing == "maths_pattern":
        report["initial_baselines"][0]["assessment_status"] = "review_required"
    elif missing == "physics_path":
        report["initial_baselines"][1]["path"] = {}
    else:
        report["assessment_catalogues"].pop("cbse-class-xii-sqp-2026-27")
    gate = evaluate_day4_acceptance(report)
    assert gate["passed"] is False
    assert gate["incomplete_components"]


def test_category_drift_with_same_marks_fails_closed(
    evidence_service: CurriculumIntelligenceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.curriculum_intelligence.baseline as baseline
    from app.curriculum_intelligence.assessment import extract_assessment_pattern

    revisions = _official_test_revisions(evidence_service)

    def changed(text: str, *, source_locator: str) -> Any:
        pattern = extract_assessment_pattern(text, source_locator=source_locator)
        if pattern.sections:
            pattern.sections[0].categories[0].code = "unspecified_response"
        return pattern

    monkeypatch.setattr(baseline, "extract_assessment_pattern", changed)
    report = official_source_demonstration(evidence_service, revisions)
    assert report["verified"] is False
    assert all(row["assessment_status"] == "review_required" for row in report["initial_baselines"])


def test_changed_marking_scheme_preserves_prior_evidence_identity(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    from copy import deepcopy

    from app.models.curriculum_intelligence import AssessmentEvidence
    from app.schemas.curriculum_intelligence import AssessmentEvidenceInput

    revisions = _official_test_revisions(evidence_service)
    report = official_source_demonstration(evidence_service, revisions)
    row = evidence_service.session.get(
        AssessmentEvidence, report["initial_baselines"][0]["assessment_evidence_id"]
    )
    assert row is not None
    original_id, original_scheme, original_json = (
        row.id,
        row.marking_scheme_revision_id,
        deepcopy(row.evidence_json),
    )
    old = revisions["cbse-maths-x-ms-2026-27"]
    assert old.source.url
    fetcher = evidence_service.source_service.fetcher
    assert isinstance(fetcher, SyntheticEvidenceFetcher)
    fetcher.contents[old.source.url] = _pdf(["041 2026 Synthetic changed marking scheme"])
    source_service = evidence_service.source_service
    changed = source_service.ingest_url(old.source_id, actor_id="test")
    changed = source_service.extract_revision(changed.id, actor_id="test")
    source_service.create_diff(changed.id, actor_id="test")
    assert source_service.validate_revision(changed.id, actor_id="test").valid
    source_service.approve_revision(changed.id, actor_id="test")
    changed = source_service.activate_revision(changed.id, actor_id="test")
    payload = AssessmentEvidenceInput(
        curriculum_version_id=row.curriculum_version_id,
        grade_node_id=row.grade_node_id,
        subject_node_id=row.subject_node_id,
        source_revision_id=row.source_revision_id,
        marking_scheme_revision_id=changed.id,
        evidence_type=row.evidence_type,
        source_locator=row.source_locator,
        evidence_json=deepcopy(row.evidence_json),
        metadata_json=deepcopy(row.metadata_json),
    )
    new_row = evidence_service.add_assessment_evidence(payload)
    evidence_service.session.commit()
    assert new_row.id != original_id
    assert new_row.marking_scheme_revision_id == changed.id
    evidence_service.session.refresh(row)
    assert row.marking_scheme_revision_id == original_scheme
    assert row.evidence_json == original_json
    assert evidence_service.add_assessment_evidence(payload).id == new_row.id
    assert (
        evidence_service.provenance(entity_type="assessment_evidence", entity_id=row.id)[
            "marking_scheme_revision_id"
        ]
        == original_scheme
    )


def test_same_evidence_binding_cannot_mutate_facts_or_use_wrong_scheme(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    from copy import deepcopy

    from app.curriculum_intelligence.service import CurriculumIntelligenceError
    from app.models.curriculum_intelligence import AssessmentEvidence
    from app.schemas.curriculum_intelligence import AssessmentEvidenceInput

    revisions = _official_test_revisions(evidence_service)
    report = official_source_demonstration(evidence_service, revisions)
    row = evidence_service.session.get(
        AssessmentEvidence, report["initial_baselines"][0]["assessment_evidence_id"]
    )
    assert row is not None
    values = dict(
        curriculum_version_id=row.curriculum_version_id,
        grade_node_id=row.grade_node_id,
        subject_node_id=row.subject_node_id,
        source_revision_id=row.source_revision_id,
        marking_scheme_revision_id=row.marking_scheme_revision_id,
        evidence_type=row.evidence_type,
        source_locator=row.source_locator,
        evidence_json=deepcopy(row.evidence_json),
        metadata_json=deepcopy(row.metadata_json),
    )
    values["evidence_json"]["competency_emphasis"] = ["Unreviewed change"]
    with pytest.raises(CurriculumIntelligenceError, match="immutable"):
        evidence_service.add_assessment_evidence(AssessmentEvidenceInput(**values))
    values["evidence_json"] = deepcopy(row.evidence_json)
    values["marking_scheme_revision_id"] = row.source_revision_id
    with pytest.raises(CurriculumIntelligenceError, match="marking-scheme source"):
        evidence_service.add_assessment_evidence(AssessmentEvidenceInput(**values))
    values["marking_scheme_revision_id"] = revisions["cbse-physics-xii-ms-2026-27"].id
    with pytest.raises(CurriculumIntelligenceError, match="supplied grade"):
        evidence_service.add_assessment_evidence(AssessmentEvidenceInput(**values))


def test_assessment_index_rejects_a_subject_absent_from_its_table(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    from app.curriculum_intelligence.service import CurriculumIntelligenceError
    from app.models.curriculum import CurriculumVersion
    from app.models.enums import CurriculumNodeType
    from app.schemas.curriculum_intelligence import AssessmentEvidenceInput, CurriculumNodeSpec

    revisions = _official_test_revisions(evidence_service)
    report = official_source_demonstration(evidence_service, revisions)
    version = evidence_service.session.get(CurriculumVersion, report["curriculum_version_id"])
    assert version is not None
    subject = evidence_service.upsert_nodes(
        version=version,
        revision=revisions["cbse-curriculum-2026-27"],
        specs=[
            CurriculumNodeSpec(
                node_type=CurriculumNodeType.SUBJECT,
                code="unlisted-subject",
                title="Unlisted Subject",
                parent_code="reviewed-x-medium",
            )
        ],
    )["unlisted-subject"]
    grade = evidence_service.hierarchy_path(subject.id)[0]
    with pytest.raises(CurriculumIntelligenceError, match="does not list supplied subject"):
        evidence_service.add_assessment_evidence(
            AssessmentEvidenceInput(
                curriculum_version_id=version.id,
                grade_node_id=grade.id,
                subject_node_id=subject.id,
                source_revision_id=revisions["cbse-class-x-sqp-2026-27"].id,
                evidence_type="sample_paper_marking_scheme_availability",
            )
        )


@pytest.mark.parametrize(
    "wording",
    [
        OUTCOME_TEXT,
        "MODEL  and solve contextualised problems\n"
        "using a pair of linear equations  and draw conclusions.",
        "Model and solve contextualised problems, using a pair of linear equations; "
        "and draw conclusions!",
    ],
)
def test_reviewed_outcome_persists_exact_original_page_span(
    evidence_service: CurriculumIntelligenceService,
    wording: str,
) -> None:
    from app.curriculum_intelligence.official_demo import _OUTCOME_LOCATOR, _exact_reviewed_outcome
    from app.curriculum_intelligence.standards_evidence import require_source_wording
    from app.models.curriculum import LearningOutcome

    revisions = _official_test_revisions(evidence_service, outcome_page=wording)
    revision = revisions["ncert-grade-9-phase-i-part-2-draft"]
    selected = _exact_reviewed_outcome(evidence_service, revision)
    assert selected == wording
    require_source_wording(
        evidence_service.source_service, revision, locator=_OUTCOME_LOCATOR, official_text=selected
    )
    report = official_source_demonstration(evidence_service, revisions)
    assert report["verified"] is True
    outcome = evidence_service.session.get(
        LearningOutcome, report["path"]["learning_outcome_ids"][0]
    )
    assert outcome is not None
    assert outcome.text == wording
    assert outcome.normalized_text == "Model contexts with paired equations; interpret solutions."
    assert outcome.source_locator == _OUTCOME_LOCATOR


@pytest.mark.parametrize(
    "outcome_page", ["No outcome on reviewed page", OUTCOME_TEXT + "\n" + OUTCOME_TEXT]
)
def test_reviewed_outcome_wrong_or_ambiguous_page_fails_without_fallback(
    evidence_service: CurriculumIntelligenceService,
    outcome_page: str,
) -> None:
    from sqlalchemy import func, select

    from app.curriculum_intelligence.official_demo import _exact_reviewed_outcome
    from app.curriculum_intelligence.standards_evidence import StandardsEvidenceError
    from app.models.curriculum import LearningOutcome

    revisions = _official_test_revisions(
        evidence_service, outcome_page=outcome_page, adjacent_page="CG-3 C-3.2 " + OUTCOME_TEXT
    )
    with pytest.raises(StandardsEvidenceError, match="missing or ambiguous"):
        _exact_reviewed_outcome(evidence_service, revisions["ncert-grade-9-phase-i-part-2-draft"])
    report = official_source_demonstration(evidence_service, revisions)
    assert report["verified"] is False
    assert report["minimum_path_verified"] is False
    assert "path" not in report
    assert evidence_service.session.scalar(select(func.count()).select_from(LearningOutcome)) == 0


@pytest.mark.parametrize("mapping_page", ["CG-3 C-3.2 and CG-3 C-3.2", "CG-3 C-3.20"])
def test_mapping_quote_ambiguous_or_wrong_identifier_returns_blocked_report(
    evidence_service: CurriculumIntelligenceService,
    mapping_page: str,
) -> None:
    from sqlalchemy import func, select

    from app.models.curriculum import EducationFramework

    revisions = _official_test_revisions(evidence_service, adjacent_page=mapping_page)
    report = official_source_demonstration(evidence_service, revisions)
    assert report["verified"] is False
    assert report["status"] == "blocked_or_review_required"
    assert "path" not in report
    assert (
        evidence_service.session.scalar(select(func.count()).select_from(EducationFramework)) == 0
    )


def test_direct_mapping_persists_literal_quote_not_normalized_commentary(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    from app.curriculum_intelligence.official_demo import _MAPPING_LOCATOR
    from app.curriculum_intelligence.standards_evidence import require_source_wording
    from app.models.framework_structure import LearningOutcomeCompetencyLink

    revisions = _official_test_revisions(evidence_service)
    report = official_source_demonstration(evidence_service, revisions)
    link_id = report["framework_structure"]["learning_outcome_links"][0]["id"]
    link = evidence_service.session.get(LearningOutcomeCompetencyLink, link_id)
    assert link is not None
    assert link.evidence_text == OUTCOME_TEXT + "\nRelevant CGs: CG-3, C-3.2"
    assert link.source_locator == _MAPPING_LOCATOR
    import hashlib
    import json

    public_link = report["framework_structure"]["learning_outcome_links"][0]
    assert "evidence_text" not in public_link
    assert (
        public_link["evidence_text_sha256"]
        == hashlib.sha256(link.evidence_text.encode()).hexdigest()
    )
    assert public_link["evidence_text_length"] == len(link.evidence_text)
    assert link.evidence_text not in json.dumps(report)
    require_source_wording(
        evidence_service.source_service,
        revisions["ncert-grade-9-phase-i-part-2-draft"],
        locator=link.source_locator,
        official_text=link.evidence_text,
    )


@pytest.mark.parametrize(
    "mapping_page",
    [
        "CG-3 C-3.2 without an explicit association label",
        "Relevant CGs: CG-3 C-3.2\n14. Mensuration\nRelevant CGs: CG-3 C-3.2",
    ],
)
def test_mapping_requires_unique_structural_row_and_explicit_association(
    evidence_service: CurriculumIntelligenceService,
    mapping_page: str,
) -> None:
    revisions = _official_test_revisions(evidence_service, adjacent_page=mapping_page)
    report = official_source_demonstration(evidence_service, revisions)
    assert report["verified"] is False
    check = next(
        check for check in report["checks"] if check["key"] == "outcome_competency_mapping"
    )
    assert check["verified"] is False
    assert "path" not in report


def test_public_quote_redaction_covers_duplicate_nested_locations() -> None:
    import json

    from app.curriculum_intelligence.official_demo import _redact_public_evidence_quotes

    quote = "Synthetic private row quote. " * 100
    report = {
        "links": [{"evidence_text": quote, "source_locator": "PDF page 56"}],
        "duplicate": {"more": [{"evidence_text": quote}]},
    }
    _redact_public_evidence_quotes(report)
    assert quote not in json.dumps(report)
    assert report["links"][0]["evidence_text_length"] == len(quote)
    assert "evidence_text" not in report["duplicate"]["more"][0]
