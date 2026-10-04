"""Reviewed initial Class X Mathematics / Class XII Physics baseline.

Normalized labels below are explicit derived groupings. Section facts were
reviewed from the official SQP instructions on PDF page 1; actual byte integrity,
header anchors and compatible extracted totals are checked again on every run.
"""

from __future__ import annotations

import io
import re
from typing import Any
from uuid import UUID

from pypdf import PdfReader

from app.curriculum_intelligence.assessment import extract_assessment_pattern
from app.curriculum_intelligence.evidence import EvidenceAnchor, check_evidence_anchors
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.curriculum import CurriculumVersion
from app.models.enums import CurriculumNodeType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import AssessmentEvidenceInput, CurriculumNodeSpec

_BASELINES = (
    {
        "key": "maths-x",
        "grade": "x",
        "subject": "Mathematics (Standard)",
        "code": "041",
        "source": "cbse-mathematics-class-x-2026-27",
        "unit": "Number Systems",
        "chapter": "Real Numbers",
        "topic": "Number properties",
        "concept": "Number property reasoning",
        "sqp": "cbse-maths-x-sqp-2026-27",
        "ms": "cbse-maths-x-ms-2026-27",
        "marks": 80,
        "questions": 38,
        "sections": [
            ("A", 20, 1, [("multiple_choice", 18), ("assertion_reason", 2)]),
            ("B", 5, 2, [("very_short_answer", 5)]),
            ("C", 6, 3, [("short_answer", 6)]),
            ("D", 4, 5, [("long_answer", 4)]),
            ("E", 3, 4, [("case_study", 3)]),
        ],
        "source_warning": None,
    },
    {
        "key": "physics-xii",
        "grade": "xii",
        "subject": "Physics",
        "code": "042",
        "source": "cbse-physics-xi-xii-2026-27",
        "unit": "Electrostatics",
        "chapter": "Electric Charges and Fields",
        "topic": "Charge and field interactions",
        "concept": "Electric field reasoning",
        "sqp": "cbse-physics-xii-sqp-2026-27",
        "ms": "cbse-physics-xii-ms-2026-27",
        "marks": 70,
        "questions": 33,
        "sections": [
            ("A", 16, 1, [("multiple_choice", 12), ("assertion_reason", 4)]),
            ("B", 5, 2, [("unspecified_response", 5)]),
            ("C", 7, 3, [("unspecified_response", 7)]),
            ("D", 2, 4, [("case_study", 2)]),
            ("E", 3, 5, [("long_answer", 3)]),
        ],
        "source_warning": "Official PDF cover has 2025-26 and 2026-27; review required",
    },
)


def seed_reviewed_baselines(
    service: CurriculumIntelligenceService,
    version: CurriculumVersion,
    revisions: dict[str, SourceRevision],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for raw in _BASELINES:
        # The constants are reviewed data, not fabricated source text or a
        # curriculum rule inferred from sample-paper contents.
        item: dict[str, Any] = dict(raw)
        key = str(item["key"])
        source_key = str(item["source"])
        grade = str(item["grade"])
        checks = check_evidence_anchors(
            service,
            revisions,
            [
                EvidenceAnchor(
                    "syllabus_heading", source_key, (str(item["unit"]), str(item["chapter"]))
                ),
            ],
        )
        report: dict[str, Any] = {
            "key": key,
            "syllabus": checks,
            "alignment_status": "unmapped",
            "source_warning": item["source_warning"],
        }
        results.append(report)
        if not checks["verified"]:
            report["status"] = "blocked_or_review_required"
            continue
        locator = f"PDF page {checks['checks'][0]['page']} > {item['unit']} > {item['chapter']}"
        chain = [
            (CurriculumNodeType.SUBJECT, str(item["subject"]), "source_subject"),
            (CurriculumNodeType.UNIT, str(item["unit"]), "source_unit"),
            (CurriculumNodeType.CHAPTER, str(item["chapter"]), "source_chapter"),
            (CurriculumNodeType.TOPIC, str(item["topic"]), "derived_topic"),
            (CurriculumNodeType.CONCEPT, str(item["concept"]), "derived_concept"),
        ]
        specs: list[CurriculumNodeSpec] = []
        parent = f"reviewed-{grade}-medium"
        subject_code = f"baseline-{key}-subject"
        for kind, title, normalization in chain:
            code = f"baseline-{key}-{kind.value}"
            specs.append(
                CurriculumNodeSpec(
                    node_type=kind,
                    code=code,
                    title=title,
                    parent_code=parent,
                    source_locator=locator,
                    metadata_json={
                        "normalization": normalization,
                        "subject_code": item["code"],
                        "review_required": bool(item["source_warning"]),
                        "source_warning": item["source_warning"],
                    },
                )
            )
            parent = code
        nodes = service.upsert_nodes(version=version, revision=revisions[source_key], specs=specs)
        subject = nodes[subject_code]
        report["path"] = service.curriculum_path(nodes[f"baseline-{key}-concept"].id).model_dump(
            mode="json"
        )
        report["status"] = (
            "source_backed_path_review_required"
            if item["source_warning"]
            else "source_backed_path_verified"
        )
        sqp_key, ms_key = str(item["sqp"]), str(item["ms"])
        pattern_checks = check_evidence_anchors(
            service,
            revisions,
            [
                EvidenceAnchor(
                    "sample_paper",
                    sqp_key,
                    (str(item["code"]), str(item["marks"]), "Section A", "Section E"),
                    page=1,
                ),
                EvidenceAnchor("marking_scheme", ms_key, (str(item["code"]), "2026"), page=1),
            ],
        )
        report["assessment_checks"] = pattern_checks
        if not pattern_checks["verified"]:
            report["assessment_status"] = "blocked_or_review_required"
            continue
        observed = extract_assessment_pattern(
            revisions[sqp_key].extracted_text or "",
            source_locator="PDF page 1 > General Instructions",
        )
        mismatches = []
        for field, expected in [
            ("total_marks", item["marks"]),
            ("total_questions", item["questions"]),
            ("duration_minutes", 180),
        ]:
            actual = getattr(observed, field)
            if actual is not None and actual != expected:
                mismatches.append(f"{field}: extracted {actual}, reviewed {expected}")
        if mismatches:
            report.update(assessment_status="review_required", unresolved_items=mismatches)
            continue
        expected_sections = {
            code: (count, count * marks) for code, count, marks, _ in item["sections"]
        }
        actual_sections = {
            section.code: (section.question_count, section.maximum_marks)
            for section in observed.sections
        }
        expected_categories = {
            code: {category: (count, marks) for category, count in categories}
            for code, _, marks, categories in item["sections"]
        }
        actual_categories = {
            section.code: {
                category.code: (category.question_count, category.marks_per_question)
                for category in section.categories
            }
            for section in observed.sections
        }
        if (
            observed.status != "verified"
            or actual_sections != expected_sections
            or actual_categories != expected_categories
        ):
            report.update(
                assessment_status="review_required",
                extracted_pattern=observed.model_dump(),
                unresolved_items=["Extracted sections differ from reviewed source facts"],
            )
            continue
        # Keep exact PDF-page locators for the parsed numeric summaries.
        revision = revisions[sqp_key]
        assert revision.storage_path is not None
        pages = PdfReader(
            io.BytesIO(service.source_service.storage.read(revision.storage_path))
        ).pages
        for section in observed.sections:
            summary = re.compile(
                rf"SECTION\s*[-–—]?\s*{section.code}\s*\(\d+\s*[x×]\s*\d+\s*=\s*\d+\)", re.I
            )
            for number, page in enumerate(pages, 1):
                if summary.search(page.extract_text() or ""):
                    section.source_locator = f"PDF page {number} > Section {section.code} summary"
                    for category in section.categories:
                        category.source_locator = "PDF page 1 > General Instructions"
                    break
        pattern = observed
        grade_node = service.hierarchy_path(subject.id)[0]
        evidence = service.add_assessment_evidence(
            AssessmentEvidenceInput(
                curriculum_version_id=UUID(version.id),
                grade_node_id=UUID(grade_node.id),
                subject_node_id=UUID(subject.id),
                source_revision_id=UUID(revisions[sqp_key].id),
                marking_scheme_revision_id=UUID(revisions[ms_key].id),
                evidence_type="assessment_pattern",
                source_locator="PDF page 1 > General Instructions",
                evidence_json=pattern.model_dump(),
                metadata_json={
                    "curriculum_membership_effect": "none",
                    "marking_scheme_source_locator": "PDF page 1 > marking scheme header",
                    "competency_emphasis_status": "not_explicitly_extracted",
                    "scope": "reviewed section counts and marks; no inferred exam blueprint",
                },
            )
        )
        report.update(
            assessment_status="verified",
            assessment_evidence_id=evidence.id,
            assessment_pattern=pattern.model_dump(),
            marking_scheme_source_revision_id=revisions[ms_key].id,
        )
    service.session.commit()
    return results
