from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_engine
from app.domain_rules import (
    PolicyConflictError,
    resolve_policy_rule,
    validate_question_diagnostic_references,
)
from app.models import (
    AdminActor,
    ApiClient,
    Institution,
    Learner,
    Organization,
    Question,
    Teacher,
)
from app.models.enums import (
    DiagnosticCategory,
    PolicyScopeType,
    QuestionOrigin,
    QuestionType,
)
from app.schemas.domain import (
    ConceptPrerequisiteGraphInput,
    ConceptPrerequisiteInput,
    CurriculumHierarchyInput,
    CurriculumNodeInput,
    DiagnosticTaxonomyInput,
    ExamSectionInput,
    ExamStructureInput,
    PolicyRuleInput,
    QuestionInput,
    QuestionOptionInput,
)


def test_settings_load_development_env_and_process_env_wins(tmp_path, monkeypatch) -> None:
    assert any(
        str(path).endswith(".env.development")
        for path in Settings.model_config["env_file"]
    )
    env_file = tmp_path / ".env.development"
    env_file.write_text(
        "API_SECRET_KEY=file-secret-value\n"
        "ANYTHINGLLM_API_KEY=file-anything-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("API_SECRET_KEY", "process-secret-value")
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    settings = Settings(_env_file=env_file)
    assert settings.api_secret_key == "process-secret-value"
    assert settings.anythingllm_api_key == "file-anything-key"


def test_curriculum_hierarchy_rejects_missing_self_and_cycles() -> None:
    version_id = uuid4()
    missing_parent = uuid4()
    with pytest.raises(ValidationError):
        CurriculumHierarchyInput(
            nodes=[
                CurriculumNodeInput(
                    curriculum_version_id=version_id,
                    parent_id=missing_parent,
                    node_type="concept",
                    code="c1",
                    title="Concept 1",
                )
            ]
        )

    node_id = uuid4()
    with pytest.raises(ValidationError):
        CurriculumHierarchyInput(
            nodes=[
                CurriculumNodeInput(
                    id=node_id,
                    curriculum_version_id=version_id,
                    parent_id=node_id,
                    node_type="concept",
                    code="self",
                    title="Self",
                )
            ]
        )

    a, b = uuid4(), uuid4()
    with pytest.raises(ValidationError):
        CurriculumHierarchyInput(
            nodes=[
                CurriculumNodeInput(
                    id=a,
                    curriculum_version_id=version_id,
                    parent_id=b,
                    node_type="topic",
                    code="a",
                    title="A",
                ),
                CurriculumNodeInput(
                    id=b,
                    curriculum_version_id=version_id,
                    parent_id=a,
                    node_type="concept",
                    code="b",
                    title="B",
                ),
            ]
        )


def test_prerequisite_graph_rejects_missing_duplicate_and_cycles() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    with pytest.raises(ValidationError):
        ConceptPrerequisiteGraphInput(
            concept_ids={a, b},
            edges=[ConceptPrerequisiteInput(prerequisite_concept_id=a, target_concept_id=c)],
        )

    edge = ConceptPrerequisiteInput(prerequisite_concept_id=a, target_concept_id=b)
    with pytest.raises(ValidationError):
        ConceptPrerequisiteGraphInput(concept_ids={a, b}, edges=[edge, edge])

    with pytest.raises(ValidationError):
        ConceptPrerequisiteGraphInput(
            concept_ids={a, b},
            edges=[
                ConceptPrerequisiteInput(prerequisite_concept_id=a, target_concept_id=b),
                ConceptPrerequisiteInput(prerequisite_concept_id=b, target_concept_id=a),
            ],
        )


def test_exam_structure_rejects_parent_cycles() -> None:
    version_id = uuid4()
    a, b = uuid4(), uuid4()
    with pytest.raises(ValidationError):
        ExamStructureInput(
            sections=[
                ExamSectionInput(
                    id=a,
                    exam_version_id=version_id,
                    parent_section_id=b,
                    code="a",
                    title="A",
                ),
                ExamSectionInput(
                    id=b,
                    exam_version_id=version_id,
                    parent_section_id=a,
                    code="b",
                    title="B",
                ),
            ]
        )


def test_question_age_metadata_and_diagnostic_references_are_validated() -> None:
    with pytest.raises(ValidationError):
        QuestionInput(
            origin_type=QuestionOrigin.GENERATED,
            question_type=QuestionType.DESCRIPTIVE,
            stem_text="Synthetic",
            age_min=18,
            age_max=12,
        )

    taxonomy = DiagnosticTaxonomyInput(
        code="FORMULA_SELECTION_ERROR",
        name="Formula selection error",
        category=DiagnosticCategory.FORMULA_KNOWLEDGE,
    )
    question = QuestionInput(
        origin_type=QuestionOrigin.GENERATED,
        question_type=QuestionType.SINGLE_CHOICE,
        stem_text="Synthetic",
        options=[
            QuestionOptionInput(
                option_key="A",
                text="Wrong",
                error_code="UNKNOWN_ERROR",
            ),
            QuestionOptionInput(option_key="B", text="Correct", is_correct=True),
        ],
    )
    with pytest.raises(ValueError, match="not defined"):
        validate_question_diagnostic_references(question, [taxonomy])


def test_policy_resolution_protects_hard_official_rules_and_is_deterministic() -> None:
    official = PolicyRuleInput(
        scope_type=PolicyScopeType.EXAM,
        scope_code="exam-x",
        policy_key="paper.question_count",
        value_json={"value": 75},
        priority=100,
        metadata_json={"enforcement": "hard"},
    )
    teacher = PolicyRuleInput(
        scope_type=PolicyScopeType.TEACHER,
        scope_code="teacher-x",
        policy_key="paper.question_count",
        value_json={"value": 20},
        priority=999,
    )
    assert resolve_policy_rule([teacher, official], "paper.question_count") is official
    assert resolve_policy_rule([official, teacher], "paper.question_count") is official

    conflicting = PolicyRuleInput(
        scope_type=PolicyScopeType.EXAM,
        scope_code="exam-y",
        policy_key="paper.question_count",
        value_json={"value": 90},
        priority=100,
        metadata_json={"enforcement": "hard"},
    )
    with pytest.raises(PolicyConflictError):
        resolve_policy_rule([official, conflicting], "paper.question_count")

    soft_official = PolicyRuleInput(
        scope_type=PolicyScopeType.EXAM,
        scope_code="exam-x",
        policy_key="question.difficulty.target",
        value_json={"value": 3},
        priority=100,
    )
    institution = PolicyRuleInput(
        scope_type=PolicyScopeType.INSTITUTION,
        scope_code="school-x",
        policy_key="question.difficulty.target",
        value_json={"value": 4},
        priority=100,
    )
    assert (
        resolve_policy_rule(
            [soft_official, institution],
            "question.difficulty.target",
        )
        is institution
    )


def test_sqlite_tenancy_relationships_are_enforced(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'tenant.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        session.add(
            Institution(
                organization_id=str(uuid4()),
                code="orphan",
                name="Orphan Institution",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_tenancy_and_question_metadata_persist(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'domain.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        org = Organization(code="org-x", name="Organization X")
        session.add(org)
        session.flush()
        institution = Institution(
            organization_id=org.id,
            code="school-x",
            name="School X",
        )
        session.add(institution)
        session.flush()
        teacher = Teacher(
            institution_id=institution.id,
            external_code="teacher-1",
            display_name="Teacher One",
        )
        learner = Learner(
            institution_id=institution.id,
            external_code="learner-1",
            display_name="Learner One",
        )
        admin = AdminActor(
            organization_id=org.id,
            institution_id=institution.id,
            external_code="admin-1",
            display_name="Admin One",
        )
        client = ApiClient(
            organization_id=org.id,
            institution_id=institution.id,
            client_code="client-1",
            name="Client One",
        )
        question = Question(
            origin_type=QuestionOrigin.GENERATED.value,
            question_type=QuestionType.DESCRIPTIVE.value,
            stem_text="Synthetic age-aware question",
            age_min=13,
            age_max=16,
            grade_year_codes=["grade-8", "grade-9"],
            rubric_json={"criteria": [{"name": "reasoning", "marks": 2}]},
        )
        session.add_all([teacher, learner, admin, client, question])
        session.commit()

        loaded = session.query(Question).filter_by(stem_text=question.stem_text).one()
        assert loaded.age_min == 13
        assert loaded.grade_year_codes == ["grade-8", "grade-9"]
        assert loaded.rubric_json["criteria"][0]["name"] == "reasoning"
        assert session.query(Teacher).count() == 1
        assert session.query(Learner).count() == 1
        assert session.query(AdminActor).count() == 1
        assert session.query(ApiClient).count() == 1
    finally:
        session.close()
        create_database_engine.cache_clear()
