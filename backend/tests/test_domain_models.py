from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models import (
    Competency,
    ConceptPrerequisite,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    DiagnosticTaxonomyEntry,
    EducationFramework,
    ExamBlueprintRule,
    ExamPack,
    ExamSection,
    ExamVersion,
    LearningOutcome,
    PolicyRule,
    Question,
    QuestionAsset,
    QuestionOption,
    Source,
    TestDefinition as AssessmentDefinition,
    TestQuestion as AssessmentQuestion,
)
from app.models.enums import (
    BlueprintRuleType,
    CognitiveLevel,
    CurriculumNodeType,
    DiagnosticCategory,
    PolicyScopeType,
    QuestionAssetType,
    QuestionOrigin,
    QuestionType,
    SourceStatus,
    SourceTrustTier,
    SourceType,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_canonical_domain_graph_persists() -> None:
    session = _session()
    try:
        source = Source(
            source_type=SourceType.OFFICIAL_SYLLABUS.value,
            title="Synthetic official source",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY.value,
            status=SourceStatus.ACTIVE.value,
        )
        framework = EducationFramework(code="framework-x", name="Framework X", country="IN")
        pack = CurriculumPack(
            code="curriculum-x",
            name="Curriculum X",
            country="IN",
            framework=framework,
        )
        version = CurriculumVersion(
            curriculum_pack=pack,
            version_code="2026-27",
            academic_year="2026-27",
            status="active",
        )
        version.sources.append(source)

        grade = CurriculumNode(
            curriculum_version=version,
            node_type=CurriculumNodeType.GRADE_YEAR.value,
            code="grade-10",
            title="Grade 10",
        )
        medium = CurriculumNode(
            curriculum_version=version,
            parent=grade,
            node_type=CurriculumNodeType.MEDIUM.value,
            code="english",
            title="English",
        )
        subject = CurriculumNode(
            curriculum_version=version,
            parent=medium,
            node_type=CurriculumNodeType.SUBJECT.value,
            code="mathematics",
            title="Mathematics",
        )
        unit = CurriculumNode(
            curriculum_version=version,
            parent=subject,
            node_type=CurriculumNodeType.UNIT.value,
            code="algebra",
            title="Algebra",
        )
        chapter = CurriculumNode(
            curriculum_version=version,
            parent=unit,
            node_type=CurriculumNodeType.CHAPTER.value,
            code="polynomials",
            title="Polynomials",
        )
        topic = CurriculumNode(
            curriculum_version=version,
            parent=chapter,
            node_type=CurriculumNodeType.TOPIC.value,
            code="factor-theorem",
            title="Factor theorem",
        )
        prerequisite = CurriculumNode(
            curriculum_version=version,
            parent=topic,
            node_type=CurriculumNodeType.CONCEPT.value,
            code="factorisation",
            title="Factorisation",
        )
        concept = CurriculumNode(
            curriculum_version=version,
            parent=topic,
            node_type=CurriculumNodeType.CONCEPT.value,
            code="factor-theorem-concept",
            title="Factor theorem concept",
        )
        outcome = LearningOutcome(
            curriculum_version=version,
            code="lo-1",
            text="Apply the factor theorem.",
        )
        competency = Competency(
            code="problem_solving",
            name="Problem solving",
        )
        concept.learning_outcomes.append(outcome)
        concept.competencies.append(competency)
        edge = ConceptPrerequisite(
            prerequisite_concept=prerequisite,
            target_concept=concept,
            weight=0.8,
        )

        exam_pack = ExamPack(code="exam-x", name="Exam X", country="IN")
        exam_version = ExamVersion(
            exam_pack=exam_pack,
            version_code="2026",
            status="active",
        )
        exam_version.sources.append(source)
        paper = ExamSection(
            exam_version=exam_version,
            code="paper-1",
            title="Paper 1",
            sequence=1,
        )
        section = ExamSection(
            exam_version=exam_version,
            parent=paper,
            code="section-a",
            title="Section A",
            sequence=1,
            subject_code="mathematics",
        )
        exact_rule = ExamBlueprintRule(
            exam_version=exam_version,
            section=section,
            rule_type=BlueprintRuleType.QUESTION_COUNT.value,
            exact_count=10,
        )
        range_rule = ExamBlueprintRule(
            exam_version=exam_version,
            section=section,
            rule_type=BlueprintRuleType.DIFFICULTY_DISTRIBUTION.value,
            min_count=2,
            max_count=4,
            selector_json={"difficulty": 5},
        )

        diagnostic = DiagnosticTaxonomyEntry(
            code="FORMULA_SELECTION_ERROR",
            name="Formula selection error",
            category=DiagnosticCategory.FORMULA_KNOWLEDGE.value,
        )
        question = Question(
            origin_type=QuestionOrigin.GENERATED.value,
            curriculum_version=version,
            exam_version=exam_version,
            primary_curriculum_node=concept,
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text="Synthetic stem",
            answer_json={"option_key": "B"},
            difficulty=3,
            cognitive_level=CognitiveLevel.APPLY.value,
        )
        question.options.extend(
            [
                QuestionOption(
                    option_key="A",
                    text="Distractor",
                    diagnostic_taxonomy_entry=diagnostic,
                    error_code="FORMULA_SELECTION_ERROR",
                    sequence=1,
                ),
                QuestionOption(option_key="B", text="Correct", is_correct=True, sequence=2),
            ]
        )
        question.assets.append(
            QuestionAsset(
                asset_type=QuestionAssetType.GRAPH.value,
                payload_json={"kind": "synthetic"},
            )
        )
        question.competencies.append(competency)
        question.learning_outcomes.append(outcome)
        question.prerequisite_concepts.append(prerequisite)
        question.sources.append(source)

        test = AssessmentDefinition(
            code="test-x",
            title="Synthetic test",
            curriculum_version=version,
            exam_version=exam_version,
            blueprint_json={"question_count": 1},
        )
        test.questions.append(
            AssessmentQuestion(question=question, sequence=1, marks=4)
        )

        policy = PolicyRule(
            scope_type=PolicyScopeType.INSTITUTION.value,
            scope_code="school-a",
            policy_key="question.difficulty.max",
            value_json={"value": 4},
            priority=300,
        )
        policy.sources.append(source)

        session.add_all(
            [
                framework,
                pack,
                version,
                grade,
                medium,
                subject,
                unit,
                chapter,
                topic,
                prerequisite,
                concept,
                outcome,
                competency,
                edge,
                exam_pack,
                exam_version,
                paper,
                section,
                exact_rule,
                range_rule,
                diagnostic,
                question,
                test,
                policy,
            ]
        )
        session.commit()

        loaded = session.query(Question).filter_by(stem_text="Synthetic stem").one()
        assert loaded.primary_curriculum_node is not None
        assert loaded.primary_curriculum_node.code == "factor-theorem-concept"
        assert loaded.options[0].error_code == "FORMULA_SELECTION_ERROR"
        assert loaded.prerequisite_concepts[0].code == "factorisation"
        assert loaded.sources[0].title == "Synthetic official source"
        assert session.query(ExamBlueprintRule).count() == 2
        assert session.query(PolicyRule).one().priority == 300
        assert session.query(AssessmentQuestion).one().marks == 4
    finally:
        session.close()
