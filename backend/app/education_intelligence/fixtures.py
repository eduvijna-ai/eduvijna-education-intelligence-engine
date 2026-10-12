from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    CanonicalRubric,
    CognitiveDemandEvidence,
    DifficultyEvidence,
    QuestionOptionInput,
    RubricCriterion,
    ValidationRunSummary,
)
from app.education_intelligence.enums import ValidationStatus
from app.models.curriculum import (
    Competency,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
    LearningOutcome,
)
from app.models.enums import CurriculumNodeType, CurriculumStatus, SourceType
from app.models.source import Source, SourceRevision


def seed_cbse_fixture_curriculum(session: Session) -> dict[str, str]:
    """Synthetic item text; real-shaped entity references for scope validation."""
    source = Source(
        source_type=SourceType.OFFICIAL_SYLLABUS.value,
        title="Synthetic CBSE syllabus reference (non-copyright fixture)",
    )
    framework = EducationFramework(code="cbse-fixture", name="CBSE Fixture", country="IN")
    pack = CurriculumPack(
        code="cbse-math-fixture",
        name="CBSE Mathematics Fixture",
        country="IN",
        framework=framework,
    )
    version = CurriculumVersion(
        curriculum_pack=pack,
        version_code="2026-27",
        status=CurriculumStatus.ACTIVE.value,
    )
    version.sources.append(source)
    session.add_all([source, framework, pack, version])
    session.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="c" * 64,
        source_snapshot_checksum="d" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum="c" * 64,
        metadata_json={"synthetic_fixture": True},
    )
    session.add(revision)
    session.flush()
    grade = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.GRADE_YEAR.value,
        code="grade-8",
        title="Grade 8",
        metadata_json={"authoritative_age_min": 12, "authoritative_age_max": 14},
    )
    medium = CurriculumNode(
        curriculum_version=version,
        parent=grade,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="english",
        title="English medium",
    )
    subject = CurriculumNode(
        curriculum_version=version,
        parent=medium,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    lo = LearningOutcome(
        curriculum_version=version,
        code="LO-MATH-01",
        text="Synthetic LO: interpret simple linear relationships (fixture only).",
        active=True,
        source_revision_id=revision.id,
    )
    lo.nodes.append(subject)
    comp = Competency(
        code="application",
        name="Application",
        framework=framework,
        active=True,
        source_revision_id=revision.id,
    )
    comp.nodes.append(subject)
    session.add_all([revision, grade, medium, subject, lo, comp])
    session.flush()
    return {
        "curriculum_version_id": version.id,
        "learning_outcome_id": lo.id,
        "subject_code": "mathematics",
        "competency_code": "application",
        "framework_id": framework.id,
    }


def seed_telangana_fixture_curriculum(session: Session) -> dict[str, str]:
    source = Source(
        source_type=SourceType.OFFICIAL_SYLLABUS.value,
        title="Synthetic Telangana syllabus reference (fixture; D5-DS01 deferred)",
    )
    framework = EducationFramework(code="tg-fixture", name="Telangana Fixture", country="IN")
    pack = CurriculumPack(
        code="tg-science-fixture",
        name="Telangana Science Fixture",
        country="IN",
        framework=framework,
    )
    version = CurriculumVersion(
        curriculum_pack=pack,
        version_code="2026-27",
        status=CurriculumStatus.ACTIVE.value,
    )
    lo = LearningOutcome(
        curriculum_version=version,
        code="LO-SCI-01",
        text="Synthetic LO: describe states of matter (fixture only).",
        active=True,
    )
    session.add_all([source, framework, pack, version, lo])
    session.flush()
    return {
        "curriculum_version_id": version.id,
        "learning_outcome_id": lo.id,
        "subject_code": "science",
    }


def positive_cbse_item(ctx_ids: dict[str, str]) -> CanonicalAssessmentItem:
    return CanonicalAssessmentItem(
        item_id="cbse-positive-001",
        stem_text="Synthetic fixture: What is 7 + 5?",
        question_type="single_choice",
        options=[
            QuestionOptionInput(option_key="A", text="11", is_correct=False),
            QuestionOptionInput(option_key="B", text="12", is_correct=True),
        ],
        declared_cognitive_level="Apply",
        competency_codes=["application"],
        learning_outcome_ids=[ctx_ids["learning_outcome_id"]],
        curriculum_version_id=ctx_ids["curriculum_version_id"],
        grade_year_code="grade-8",
        medium_code="english",
        subject_code=ctx_ids["subject_code"],
        declared_difficulty=2,
        difficulty_evidence=DifficultyEvidence(
            cognitive_demand_band=2,
            step_count=1,
            computation_load=2,
            language_load=1,
        ),
        cognitive_demand_evidence=CognitiveDemandEvidence(application_required=True),
        age_min=12,
        age_max=14,
        answer_metadata_present=True,
        metadata_json={"synthetic_fixture": True, "official_curriculum_text": False},
    )


def adversarial_wrong_lo_version(ctx_ids: dict[str, str]) -> CanonicalAssessmentItem:
    item = positive_cbse_item(ctx_ids)
    return item.model_copy(
        update={
            "item_id": "adv-wrong-lo",
            "curriculum_version_id": "00000000-0000-0000-0000-000000000099",
        }
    )


def adversarial_cognitive_mismatch(ctx_ids: dict[str, str]) -> CanonicalAssessmentItem:
    return positive_cbse_item(ctx_ids).model_copy(
        update={
            "item_id": "adv-cog-mismatch",
            "declared_cognitive_level": "Remember",
            "cognitive_demand_evidence": CognitiveDemandEvidence(
                multi_step_reasoning=True,
                comparison_or_evaluation=True,
            ),
        }
    )


def adversarial_broken_rubric(ctx_ids: dict[str, str]) -> CanonicalAssessmentItem:
    return positive_cbse_item(ctx_ids).model_copy(
        update={
            "item_id": "adv-rubric",
            "rubric": CanonicalRubric(
                total_marks=10,
                criteria=[
                    RubricCriterion(
                        criterion_id="c1",
                        title="Explanation",
                        marks=4,
                        performance_levels=[{"label": "Good", "score": 4}],
                    ),
                    RubricCriterion(
                        criterion_id="c2",
                        title="Method",
                        marks=3,
                        performance_levels=[],
                    ),
                ],
            ),
        }
    )


def adversarial_safety_trigger(ctx_ids: dict[str, str]) -> CanonicalAssessmentItem:
    return positive_cbse_item(ctx_ids).model_copy(
        update={
            "item_id": "adv-safety",
            "content_text_for_safety": (
                "Perform this unsafe lab experiment at home without supervision."
            ),
        }
    )


def adversarial_invalid_progression(ctx_ids: dict[str, str]) -> CanonicalAssessmentItem:
    return positive_cbse_item(ctx_ids).model_copy(
        update={
            "item_id": "adv-progression",
            "cognitive_progression": ["evaluate", "remember", "apply"],
        }
    )


def assert_blocking_failure(
    summary: ValidationRunSummary, rule_fragment: str | None = None
) -> None:
    assert summary.aggregate_status in {
        ValidationStatus.FAIL,
        ValidationStatus.REVIEW_REQUIRED,
    } or summary.blocking_failure
    if rule_fragment:
        codes = [c for r in summary.results for c in r.rule_codes]
        assert any(rule_fragment in c for c in codes)
