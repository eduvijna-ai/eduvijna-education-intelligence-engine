"""A bounded official-content demonstration, distinct from synthetic fixtures."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.curriculum_intelligence.evidence import EvidenceAnchor, check_evidence_anchors
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.enums import CurriculumNodeType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import (
    AssessmentEvidenceInput,
    CompetencySpec,
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
    LearningOutcomeSpec,
)

OUTCOME_TEXT = (
    "Model and solve contextualised problems using a pair of linear equations and draw conclusions."
)


def official_source_demonstration(
    service: CurriculumIntelligenceService,
    revisions: dict[str, SourceRevision],
) -> dict[str, Any]:
    """Build only after actual bytes and reviewed page anchors all match.

    NCERT's Grade 9 publication is a draft. Its outcome stays draft evidence;
    the concept-to-outcome relationship is explicitly derived/partial. This
    proves a source-backed path, never full catalogue or final NCERT approval.
    """
    ncf_key = "ncfse-2023-ncert-official"
    ncert_key = "ncert-grade-9-phase-i-part-2-draft"
    cbse_key = "cbse-mathematics-class-ix-2026-27"
    index_key = "cbse-curriculum-2026-27"
    sqp_key = "cbse-class-x-sqp-2026-27"
    report = check_evidence_anchors(
        service,
        revisions,
        [
            EvidenceAnchor("framework", ncf_key, ("National Curriculum Framework", "2023")),
            EvidenceAnchor("competency", ncert_key, ("C-3.2", "CG-3"), page=46),
            EvidenceAnchor("outcome", ncert_key, (OUTCOME_TEXT,), page=56),
            EvidenceAnchor("outcome_competency_mapping", ncert_key, ("C-3.2", "CG-3"), page=57),
            EvidenceAnchor(
                "cbse_syllabus", cbse_key, ("Linear Equations in Two Variables", "C-3.2")
            ),
            EvidenceAnchor("academic_version", index_key, ("2026-27", "Mathematics")),
            EvidenceAnchor(
                "assessment_availability", sqp_key, ("Mathematics", "Standard", "SQP", "MS")
            ),
        ],
    )
    report["publication_status"] = {"ncert_grade_9": "draft", "cbse": "2026-27"}
    report["complete_catalogue"] = False
    report["status"] = "blocked_or_review_required"
    if not report["verified"]:
        return report

    checks = {check["key"]: check for check in report["checks"]}
    framework = service.ensure_framework(
        code="ncfse-2023-content-demonstration",
        name="National Curriculum Framework for School Education 2023",
        country="India",
        authority="NCERT / Ministry of Education",
        version_code="2023",
        revision=revisions[ncf_key],
        source_locator=f"PDF page {checks['framework']['page']}",
    )
    pack = service.ensure_pack(
        framework=framework,
        code="cbse-content-demonstration",
        name="CBSE",
        authority="Central Board of Secondary Education",
        country="India",
        revision=revisions[index_key],
        source_locator="Curriculum 2026-27 official index",
        metadata_json={"scope": "bounded reviewed demonstration", "complete_catalogue": False},
    )
    version = service.ensure_version(
        pack=pack,
        version_code="2026-27",
        academic_year="2026-27",
        revision=revisions[index_key],
        source_locator="Curriculum 2026-27 official index",
        metadata_json={"source_backed_demonstration": True, "complete_catalogue": False},
    )
    competency = service.upsert_competencies(
        framework=framework,
        revision=revisions[ncert_key],
        specs=[
            CompetencySpec(
                code="ncf2023-math-cg3-c32-reviewed-draft",
                name="Model contextual problems using equations",
                description="Normalized label; original competency located by its official code.",
                source_locator="PDF page 46 > Mathematics > CG-3 > C-3.2",
                metadata_json={
                    "official_code": "C-3.2",
                    "curricular_goal": "CG-3",
                    "curricular_area": "Mathematics",
                    "stage": "Secondary",
                    "publication_status": "draft",
                    "normalization": "derived_label",
                },
            )
        ],
    )["ncf2023-math-cg3-c32-reviewed-draft"]
    outcome = service.upsert_learning_outcomes(
        version=version,
        revision=revisions[ncert_key],
        specs=[
            LearningOutcomeSpec(
                code="ncert-grade9-linear-equations-draft",
                text=OUTCOME_TEXT,
                normalized_text="Model contexts with paired equations; interpret solutions.",
                source_locator="PDF pages 56-57 > row 13 > outcome/competency mapping",
                metadata_json={
                    "publication_status": "draft",
                    "grade": "IX",
                    "stage": "Secondary",
                    "subject": "Mathematics",
                    "competency_code": "C-3.2",
                    "wording_kind": "official_draft_learning_outcome",
                },
            )
        ],
    )["ncert-grade9-linear-equations-draft"]
    locator = f"PDF page {checks['cbse_syllabus']['page']} > Linear Equations in Two Variables"
    chain = [
        (CurriculumNodeType.GRADE_YEAR, "ix", "Class IX", "source_grade"),
        (CurriculumNodeType.MEDIUM, "common", "Source not medium-specific", "derived_placeholder"),
        (CurriculumNodeType.SUBJECT, "math", "Mathematics", "source_subject"),
        (CurriculumNodeType.UNIT, "algebra", "Algebra", "derived_grouping"),
        (
            CurriculumNodeType.CHAPTER,
            "linear-equations",
            "Linear Equations in Two Variables",
            "source_heading",
        ),
        (
            CurriculumNodeType.TOPIC,
            "contextual-models",
            "Contextual equation models",
            "derived_topic",
        ),
        (
            CurriculumNodeType.CONCEPT,
            "paired-equations",
            "Solving paired linear equations",
            "derived_concept",
        ),
    ]
    specs: list[CurriculumNodeSpec] = []
    parent: str | None = None
    for node_type, code, title, normalization in chain:
        code = "reviewed-ix-" + code
        specs.append(
            CurriculumNodeSpec(
                node_type=node_type,
                code=code,
                title=title,
                parent_code=parent,
                source_locator=locator,
                metadata_json={"normalization": normalization, "complete_catalogue": False},
            )
        )
        parent = code
    nodes = service.upsert_nodes(version=version, revision=revisions[cbse_key], specs=specs)
    concept = nodes["reviewed-ix-paired-equations"]
    for target_kind, target_id in (
        ("learning_outcome_id", outcome.id),
        ("competency_id", competency.id),
    ):
        payload = {
            "curriculum_version_id": version.id,
            "curriculum_node_id": concept.id,
            target_kind: target_id,
            "relationship_type": "addresses",
            "status": "partial",
            "inferred": True,
            "confidence": None,
            "source_revision_id": revisions[ncert_key].id,
            "source_locator": "PDF pages 56-57 > row 13",
            "evidence_text": "Draft outcome/competency link; concept mapping is derived.",
            "metadata_json": {"publication_status": "draft", "reviewed_anchor_checks": True},
        }
        service.align(CurriculumAlignmentInput.model_validate(payload))
    # Other grade roots preserve the locked IX-XII scope. Only the IX path
    # has detailed content coverage; no chapters are invented for other grades.
    grade_specs: list[CurriculumNodeSpec] = []
    for grade in ("x", "xi", "xii"):
        grade_code = f"reviewed-{grade}-grade"
        medium_code = f"reviewed-{grade}-medium"
        grade_specs.extend(
            [
                CurriculumNodeSpec(
                    node_type=CurriculumNodeType.GRADE_YEAR,
                    code=grade_code,
                    title=f"Class {grade.upper()}",
                    source_locator="Curriculum index scope",
                    metadata_json={"content_coverage": "representative_subject_only"},
                ),
                CurriculumNodeSpec(
                    node_type=CurriculumNodeType.MEDIUM,
                    code=medium_code,
                    title="Source not medium-specific",
                    parent_code=grade_code,
                    source_locator="Canonical normalization",
                    metadata_json={"normalization": "derived_placeholder"},
                ),
                CurriculumNodeSpec(
                    node_type=CurriculumNodeType.SUBJECT,
                    code=f"reviewed-{grade}-math",
                    title="Mathematics",
                    parent_code=medium_code,
                    source_locator="Curriculum index > Mathematics",
                    metadata_json={"content_coverage": "no_detailed_chapters_seeded"},
                ),
            ]
        )
    scope_nodes = service.upsert_nodes(
        version=version, revision=revisions[index_key], specs=grade_specs
    )
    assessment = service.add_assessment_evidence(
        AssessmentEvidenceInput(
            curriculum_version_id=UUID(version.id),
            grade_node_id=UUID(scope_nodes["reviewed-x-grade"].id),
            subject_node_id=UUID(scope_nodes["reviewed-x-math"].id),
            source_revision_id=UUID(revisions[sqp_key].id),
            evidence_type="sample_paper_marking_scheme_availability",
            source_locator="Class X > Mathematics (Standard) > SQP / MS",
            evidence_json={
                "sample_question_paper_published": True,
                "marking_scheme_published": True,
                "curriculum_membership_effect": "none",
                "pattern_details": "unresolved",
            },
            metadata_json={"not_a_syllabus_rule": True},
        )
    )
    service.session.commit()
    report.update(
        status="source_backed_path_verified",
        framework_id=framework.id,
        curriculum_version_id=version.id,
        path=service.curriculum_path(concept.id).model_dump(mode="json"),
        learning_outcome_id=outcome.id,
        competency_id=competency.id,
        alignment_status="partial",
        prerequisites=[],
        assessment_evidence_id=assessment.id,
        entity_counts=service.entity_counts(version.id),
        coverage=service.coverage(version.id).model_dump(),
        limitations=[
            "Draft NCERT wording retained as draft",
            "Derived concept alignment is partial",
            "This is a representative path, not full CBSE coverage",
        ],
    )
    return report
