from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine, enable_sqlite_foreign_keys
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
)
from app.models import TestDefinition as AssessmentDefinition
from app.models import TestQuestion as AssessmentQuestion
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
    enable_sqlite_foreign_keys(engine)
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


def test_sqlite_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'fk.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    session = Session(engine)
    try:
        session.add(
            QuestionOption(
                question_id="00000000-0000-0000-0000-000000000000",
                option_key="A",
                text="orphan",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def _integrity_session(tmp_path: Path, name: str) -> tuple[Session, object]:
    database_url = f"sqlite:///{tmp_path / name}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    return Session(engine), engine


def test_curriculum_root_code_is_unique_across_node_types(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "root-unique.db")
    try:
        pack = CurriculumPack(code="root-pack", name="Root Pack", country="IN")
        version = CurriculumVersion(curriculum_pack=pack, version_code="v1")
        version.nodes.extend(
            [
                CurriculumNode(
                    node_type=CurriculumNodeType.GRADE_YEAR.value,
                    code="same-root-code",
                    title="Root A",
                ),
                CurriculumNode(
                    node_type=CurriculumNodeType.SUBJECT.value,
                    code="same-root-code",
                    title="Root B",
                ),
            ]
        )
        session.add(pack)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_curriculum_sibling_code_is_unique_across_node_types(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "sibling-unique.db")
    try:
        pack = CurriculumPack(code="sibling-pack", name="Sibling Pack", country="IN")
        version = CurriculumVersion(curriculum_pack=pack, version_code="v1")
        parent = CurriculumNode(
            curriculum_version=version,
            node_type=CurriculumNodeType.GRADE_YEAR.value,
            code="parent",
            title="Parent",
        )
        parent.children.extend(
            [
                CurriculumNode(
                    curriculum_version=version,
                    node_type=CurriculumNodeType.SUBJECT.value,
                    code="same-child-code",
                    title="Child A",
                ),
                CurriculumNode(
                    curriculum_version=version,
                    node_type=CurriculumNodeType.UNIT.value,
                    code="same-child-code",
                    title="Child B",
                ),
            ]
        )
        session.add(pack)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_curriculum_parent_cannot_cross_versions(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "cross-version.db")
    try:
        pack = CurriculumPack(code="cross-pack", name="Cross Pack", country="IN")
        version_a = CurriculumVersion(curriculum_pack=pack, version_code="a")
        version_b = CurriculumVersion(curriculum_pack=pack, version_code="b")
        parent = CurriculumNode(
            curriculum_version=version_a,
            node_type=CurriculumNodeType.GRADE_YEAR.value,
            code="parent-a",
            title="Parent A",
        )
        child = CurriculumNode(
            curriculum_version=version_b,
            parent=parent,
            node_type=CurriculumNodeType.SUBJECT.value,
            code="child-b",
            title="Child B",
        )
        session.add_all([pack, parent, child])
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_blueprint_exact_count_must_fit_persisted_range(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "blueprint-range.db")
    try:
        pack = ExamPack(code="range-pack", name="Range Pack", country="IN")
        version = ExamVersion(exam_pack=pack, version_code="v1")
        version.blueprint_rules.append(
            ExamBlueprintRule(
                rule_type=BlueprintRuleType.QUESTION_COUNT.value,
                exact_count=5,
                min_count=10,
                max_count=20,
            )
        )
        session.add(pack)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()



def test_exam_section_parent_cannot_cross_versions(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "exam-section-cross-version.db")
    try:
        pack = ExamPack(code="exam-section-pack", name="Exam Section Pack", country="IN")
        version_a = ExamVersion(exam_pack=pack, version_code="a")
        version_b = ExamVersion(exam_pack=pack, version_code="b")
        parent = ExamSection(
            exam_version=version_a,
            code="parent-a",
            title="Parent A",
            sequence=1,
        )
        session.add_all([pack, parent])
        session.commit()

        child = ExamSection(
            exam_version=version_b,
            parent_section_id=parent.id,
            parent_exam_version_id=version_a.id,
            code="child-b",
            title="Child B",
            sequence=1,
        )
        session.add(child)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_blueprint_section_cannot_cross_exam_versions(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "blueprint-section-cross-version.db")
    try:
        pack = ExamPack(code="blueprint-section-pack", name="Blueprint Section Pack", country="IN")
        version_a = ExamVersion(exam_pack=pack, version_code="a")
        version_b = ExamVersion(exam_pack=pack, version_code="b")
        section_b = ExamSection(
            exam_version=version_b,
            code="section-b",
            title="Section B",
            sequence=1,
        )
        session.add_all([pack, section_b])
        session.commit()

        rule = ExamBlueprintRule(
            exam_version=version_a,
            section_id=section_b.id,
            section_exam_version_id=version_b.id,
            rule_type=BlueprintRuleType.QUESTION_COUNT.value,
            exact_count=5,
        )
        session.add(rule)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_prerequisite_edges_require_concept_nodes(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "concept-only-prerequisite.db")
    try:
        pack = CurriculumPack(code="concept-only-pack", name="Concept Only Pack", country="IN")
        version = CurriculumVersion(curriculum_pack=pack, version_code="v1")
        unit = CurriculumNode(
            curriculum_version=version,
            node_type=CurriculumNodeType.UNIT.value,
            code="unit",
            title="Unit",
        )
        concept = CurriculumNode(
            curriculum_version=version,
            node_type=CurriculumNodeType.CONCEPT.value,
            code="concept",
            title="Concept",
        )
        session.add_all([pack, unit, concept])
        session.commit()

        session.add(
            ConceptPrerequisite(
                prerequisite_concept_id=unit.id,
                target_concept_id=concept.id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_question_prerequisites_require_concept_nodes(tmp_path: Path) -> None:
    session, _ = _integrity_session(tmp_path, "question-concept-only.db")
    try:
        pack = CurriculumPack(
            code="question-concept-pack",
            name="Question Concept Pack",
            country="IN",
        )
        version = CurriculumVersion(curriculum_pack=pack, version_code="v1")
        unit = CurriculumNode(
            curriculum_version=version,
            node_type=CurriculumNodeType.UNIT.value,
            code="unit",
            title="Unit",
        )
        question = Question(
            origin_type=QuestionOrigin.GENERATED.value,
            question_type=QuestionType.DESCRIPTIVE.value,
            stem_text="Concept-only association test",
            answer_json={},
        )
        question.prerequisite_concepts.append(unit)
        session.add_all([pack, question])
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()
