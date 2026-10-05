"""A bounded official-content demonstration, distinct from synthetic fixtures."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from app.curriculum_intelligence.acceptance import evaluate_day4_acceptance
from app.curriculum_intelligence.baseline import seed_reviewed_baselines
from app.curriculum_intelligence.catalogue import CatalogueExtractionError, extract_stored_index
from app.curriculum_intelligence.evidence import EvidenceAnchor, check_evidence_anchors
from app.curriculum_intelligence.framework_structure import FrameworkStructureService
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.curriculum_intelligence.standards_evidence import (
    StandardsEvidenceError,
    contains_complete_identifier,
    source_text_at_locator,
)
from app.models.enums import CurriculumNodeType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import (
    AssessmentEvidenceInput,
    CompetencySpec,
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
    LearningOutcomeSpec,
)
from app.schemas.framework_structure import FrameworkNodeSpec, LearningOutcomeCompetencyInput

OUTCOME_TEXT = (
    "Model and solve contextualised problems using a pair of linear equations and draw conclusions."
)


_OUTCOME_LOCATOR = "PDF page 56 > row 13 > outcome wording"


def _exact_reviewed_outcome(
    service: CurriculumIntelligenceService, revision: SourceRevision
) -> str:
    """Select one literal quote using the reviewed anchor on its fixed page.

    Token comparison only locates the span; it never becomes persisted wording.
    Original case, punctuation and layout inside that span remain untouched.
    """
    located = source_text_at_locator(
        service.source_service,
        revision,
        locator=_OUTCOME_LOCATOR,
    )
    reviewed_words = re.findall(r"\w+", OUTCOME_TEXT.casefold())
    tokens = list(re.finditer(r"\w+", located))
    matches: list[tuple[int, int]] = []
    width = len(reviewed_words)
    for index in range(len(tokens) - width + 1):
        window = tokens[index : index + width]
        if [token.group().casefold() for token in window] == reviewed_words:
            start, end = window[0].start(), window[-1].end()
            # Include original terminal sentence punctuation when present,
            # without absorbing following rows or their wording.
            terminal = re.match(r"[ \t]*[.!?]", located[end:])
            if terminal:
                end += terminal.end()
            matches.append((start, end))
    if len(matches) != 1:
        raise StandardsEvidenceError(
            "Reviewed outcome quote is missing or ambiguous on PDF page 56"
        )
    start, end = matches[0]
    return located[start:end]


_MAPPING_LOCATOR = "PDF pages 56-57 > reviewed row 13 outcome/competency mapping"


def _exact_reviewed_mapping(
    service: CurriculumIntelligenceService, revision: SourceRevision, outcome_text: str
) -> str:
    """Preserve the original reviewed row span; ambiguous anchors need review.

    Fixed pages and the pre-existing reviewed row association are mandatory.
    Presence elsewhere in the document never repairs a missing mapping anchor.
    """
    located = source_text_at_locator(service.source_service, revision, locator=_MAPPING_LOCATOR)
    starts = list(
        re.finditer(r"\b13\.\s+Linear\s+Equations\s+in\s+Two\s+Variables\b", located, re.I)
    )
    ends = list(re.finditer(r"\b14\.\s+Mensuration\b", located, re.I))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() >= ends[0].start():
        raise StandardsEvidenceError(
            "Reviewed row 13/14 structural boundaries missing or ambiguous on PDF pages 56-57"
        )
    located = located[starts[0].start() : ends[0].start()]
    outcomes = list(re.finditer(re.escape(outcome_text), located))
    identifiers: list[re.Match[str]] = []
    for identifier in ("CG-3", "C-3.2"):
        matches = [
            match
            for match in re.finditer(re.escape(identifier), located)
            if contains_complete_identifier(
                located[max(0, match.start() - 2) : match.end() + 2], identifier
            )
        ]
        if len(matches) != 1:
            raise StandardsEvidenceError(
                "Reviewed mapping identifier is absent or ambiguous on PDF pages 56-57"
            )
        identifiers.extend(matches)
    if len(outcomes) != 1:
        raise StandardsEvidenceError("Reviewed outcome is absent or ambiguous in mapping range")
    declarations = list(re.finditer(r"Relevant\s+CGs\s*:", located, re.I))
    if len(declarations) != 1 or not all(
        match.start() >= declarations[0].end() for match in identifiers
    ):
        raise StandardsEvidenceError("Reviewed row has no unique explicit competency association")
    anchors = [outcomes[0], *identifiers]
    return located[min(match.start() for match in anchors) : max(match.end() for match in anchors)]


def _redact_public_evidence_quotes(value: Any) -> None:
    """Keep original quotations in the private DB, not public verifier artifacts."""
    if isinstance(value, dict):
        quote = value.get("evidence_text")
        if isinstance(quote, str):
            value.pop("evidence_text")
            value["evidence_text_sha256"] = hashlib.sha256(quote.encode("utf-8")).hexdigest()
            value["evidence_text_length"] = len(quote)
        for child in value.values():
            _redact_public_evidence_quotes(child)
    elif isinstance(value, list):
        for child in value:
            _redact_public_evidence_quotes(child)


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
    report["minimum_path_verified"] = report["verified"]
    report["publication_status"] = {"ncert_grade_9": "draft", "cbse": "2026-27"}
    report["complete_catalogue"] = False
    report["status"] = "blocked_or_review_required"
    if not report["verified"]:
        report["acceptance"] = evaluate_day4_acceptance(report)
        return report

    checks = {check["key"]: check for check in report["checks"]}
    checked_quote = "outcome"
    try:
        outcome_text = _exact_reviewed_outcome(service, revisions[ncert_key])
        checked_quote = "outcome_competency_mapping"
        mapping_text = _exact_reviewed_mapping(service, revisions[ncert_key], outcome_text)
    except StandardsEvidenceError as exc:
        checks[checked_quote].update(verified=False, reason=str(exc))
        report["verified"] = False
        report["minimum_path_verified"] = False
        report["acceptance"] = evaluate_day4_acceptance(report)
        return report
    framework = service.ensure_framework(
        code="ncfse-2023",
        name="National Curriculum Framework for School Education 2023",
        country="India",
        authority="NCERT / Ministry of Education",
        version_code="2023",
        revision=revisions[ncf_key],
        source_locator=f"PDF page {checks['framework']['page']}",
    )
    pack = service.ensure_pack(
        framework=framework,
        code="cbse",
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
                text=outcome_text,
                normalized_text="Model contexts with paired equations; interpret solutions.",
                source_locator=_OUTCOME_LOCATOR,
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
    structure_service = FrameworkStructureService(
        service.session, source_service=service.source_service
    )
    framework_specs = []
    parent_code = None
    for level, code, title, official_code in (
        ("stage", "secondary", "Secondary stage", None),
        ("curricular_area", "secondary-mathematics", "Mathematics", None),
        ("goal", "secondary-mathematics-cg3", "Algebraic modeling", "CG-3"),
        ("competency", "secondary-mathematics-cg3-c32", "Contextual equation models", "C-3.2"),
    ):
        framework_specs.append(
            FrameworkNodeSpec.model_validate(
                {
                    "level": level,
                    "code": code,
                    "title": title,
                    "official_code": official_code,
                    "parent_code": parent_code,
                    "competency_id": competency.id if level == "competency" else None,
                    "source_locator": "NCERT Grade9 draft PDF page46; normalized hierarchy labels",
                    "publication_status": "draft",
                    "review_status": "reviewed",
                    "inferred": False,
                }
            )
        )
        parent_code = code
    # Standards establish competency leaves, never a framework's roots.
    # The scaffold is explicitly a derived organization under the governing NCF;
    # no NCERT draft CG code is presented as an NCF goal identifier.
    scaffold = [
        spec.model_copy(
            update={
                "official_code": None,
                "source_locator": (
                    f"NCFSE PDF page {checks['framework']['page']}; derived scaffold labels"
                ),
                "publication_status": "final",
                "inferred": True,
            }
        )
        for spec in framework_specs[:-1]
    ]
    structure = structure_service.upsert_nodes(
        framework=framework,
        revision=revisions[ncf_key],
        specs=scaffold,
    )
    structure.update(
        structure_service.upsert_nodes(
            framework=framework,
            revision=revisions[ncert_key],
            specs=framework_specs[-1:],
        )
    )
    competency_node = structure["secondary-mathematics-cg3-c32"]
    structure_service.link_learning_outcome(
        LearningOutcomeCompetencyInput(
            curriculum_version_id=UUID(version.id),
            learning_outcome_id=UUID(outcome.id),
            competency_node_id=UUID(competency_node.id),
            source_revision_id=UUID(revisions[ncert_key].id),
            source_locator=_MAPPING_LOCATOR,
            publication_status="draft",
            review_status="reviewed",
            status="direct",
            inferred=False,
            evidence_text=mapping_text,
        )
    )
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
                "subject": "Mathematics (Standard)",
                "curriculum_membership_effect": "none",
                "pattern_details": "unresolved",
            },
            metadata_json={"not_a_syllabus_rule": True},
        )
    )
    catalogue_report: dict[str, Any]
    try:
        catalogue_report = extract_stored_index(service, revisions[index_key], kind="curriculum")
        materialized: list[str] = []
        for entry in catalogue_report["subjects"]:
            if entry["grade_scope"] != "explicit_single" or entry["review_required"]:
                continue
            grade = entry["grade_candidates"][0].lower()
            medium = "reviewed-ix-common" if grade == "ix" else f"reviewed-{grade}-medium"
            if grade not in {"ix", "x", "xi", "xii"}:
                continue
            item = service.upsert_nodes(
                version=version,
                revision=revisions[index_key],
                specs=[
                    CurriculumNodeSpec(
                        node_type=CurriculumNodeType.SUBJECT,
                        code="index-" + entry["key"][:40],
                        title=entry["subject_label"],
                        parent_code=medium,
                        source_locator=entry["source_locator"][:1024],
                        metadata_json={
                            "catalogue_entry_key": entry["key"],
                            "official_document_url": entry["url"],
                            "content_coverage": "catalogue_only",
                            "review_required": False,
                        },
                    )
                ],
            )
            materialized.extend(node.id for node in item.values())
        catalogue_report["materialized_subject_node_ids"] = materialized
        catalogue_report["coverage_denominator"] = {
            "expected_index_entries": catalogue_report["index_subject_count"],
            "materialized_explicit_grade_entries": len(materialized),
            "not_materialized_entries": catalogue_report["index_subject_count"] - len(materialized),
            "detailed_syllabus_paths": 0,
            "unresolved_shared_grade_scope": sum(
                item["grade_scope"] == "shared" for item in catalogue_report["subjects"]
            ),
        }
    except CatalogueExtractionError as exc:
        catalogue_report = {"status": "review_required", "reason": str(exc)}
    assessment_catalogues = {}
    for source_key in ("cbse-class-x-sqp-2026-27", "cbse-class-xii-sqp-2026-27"):
        source_revision = revisions.get(source_key)
        if source_revision is None:
            continue
        try:
            assessment_catalogues[source_key] = extract_stored_index(
                service, source_revision, kind="assessment"
            )
        except CatalogueExtractionError as exc:
            assessment_catalogues[source_key] = {"status": "review_required", "reason": str(exc)}
    baselines = seed_reviewed_baselines(service, version, revisions)
    if catalogue_report.get("extraction_verified"):
        catalogue_report["coverage_denominator"]["detailed_syllabus_paths"] = 1 + sum(
            bool(item.get("path") and item.get("syllabus", {}).get("verified"))
            for item in baselines
        )
        version.metadata_json = {**version.metadata_json, "source_catalogue": catalogue_report}
    service.session.commit()
    report.update(
        status="source_backed_path_verified",
        framework_id=framework.id,
        framework_structure=structure_service.path_for_competency(
            competency_node.id, curriculum_version_id=version.id
        ).model_dump(mode="json"),
        curriculum_version_id=version.id,
        path=service.curriculum_path(concept.id).model_dump(mode="json"),
        learning_outcome_id=outcome.id,
        competency_id=competency.id,
        alignment_status="partial",
        prerequisites=[],
        assessment_evidence_id=assessment.id,
        catalogue_inventory=catalogue_report,
        assessment_catalogues=assessment_catalogues,
        initial_baselines=baselines,
        entity_counts=service.entity_counts(version.id),
        coverage=service.coverage(version.id).model_dump(),
        limitations=[
            "Draft NCERT wording retained as draft",
            "Derived concept alignment is partial",
            "This is a representative path, not full CBSE coverage",
        ],
    )
    report["acceptance"] = evaluate_day4_acceptance(report)
    report["verified"] = report["acceptance"]["passed"]
    report["status"] = (
        "initial_scope_verified_with_source_reviews"
        if report["verified"]
        else "initial_scope_incomplete"
    )
    _redact_public_evidence_quotes(report)
    return report
