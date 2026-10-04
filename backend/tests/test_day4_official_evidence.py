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
        stream.set_data(f"BT /F1 9 Tf 20 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class SyntheticEvidenceFetcher(SourceUrlFetcher):
    """Synthetic transport for contract tests; never used in live verification."""

    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents

    def fetch(self, url: str) -> FetchedSource:
        return FetchedSource(self.contents[url], url, "application/pdf", "synthetic.pdf")


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


def _official_test_revisions(service: CurriculumIntelligenceService) -> dict[str, Any]:
    pages = ["Synthetic page"] * 57
    pages[45] = "Mathematics CG-3 C-3.2"
    pages[55] = OUTCOME_TEXT
    pages[56] = "CG-3 C-3.2"
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
        contents[f"cbse-{key}-sqp-2026-27"] = _pdf([header + section_text])
        contents[f"cbse-{key}-ms-2026-27"] = _pdf([f"{code} 2026 Marking Scheme"])
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
    assert first["status"] == "source_backed_path_verified"
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
