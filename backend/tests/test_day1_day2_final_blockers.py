from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_database_engine
from app.models import AdminActor, ApiClient, Institution, Learner, Organization, Teacher
from app.models.enums import PaperMode, QuestionOrigin, QuestionType, TestStatus
from app.schemas.domain import QuestionInput, TestDefinitionInput


def _new_session(tmp_path: Path, name: str) -> Session:
    database_url = f"sqlite:///{tmp_path / name}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_learner_primary_teacher_must_belong_to_same_institution(tmp_path: Path) -> None:
    session = _new_session(tmp_path, "learner-tenant.db")
    try:
        org = Organization(code="org", name="Org")
        session.add(org)
        session.flush()
        institution_a = Institution(organization_id=org.id, code="a", name="A")
        institution_b = Institution(organization_id=org.id, code="b", name="B")
        session.add_all([institution_a, institution_b])
        session.flush()
        teacher_b = Teacher(
            institution_id=institution_b.id,
            external_code="teacher-b",
            display_name="Teacher B",
        )
        session.add(teacher_b)
        session.flush()
        session.add(
            Learner(
                institution_id=institution_a.id,
                primary_teacher_id=teacher_b.id,
                external_code="learner-a",
                display_name="Learner A",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


@pytest.mark.parametrize("actor_kind", ["admin", "api_client"])
def test_actor_institution_must_belong_to_actor_organization(
    tmp_path: Path,
    actor_kind: str,
) -> None:
    session = _new_session(tmp_path, f"{actor_kind}-tenant.db")
    try:
        org_a = Organization(code="org-a", name="Org A")
        org_b = Organization(code="org-b", name="Org B")
        session.add_all([org_a, org_b])
        session.flush()
        institution_b = Institution(
            organization_id=org_b.id,
            code="institution-b",
            name="Institution B",
        )
        session.add(institution_b)
        session.flush()

        if actor_kind == "admin":
            session.add(
                AdminActor(
                    organization_id=org_a.id,
                    institution_id=institution_b.id,
                    external_code="admin-x",
                    display_name="Admin X",
                )
            )
        else:
            session.add(
                ApiClient(
                    organization_id=org_a.id,
                    institution_id=institution_b.id,
                    client_code="client-x",
                    name="Client X",
                )
            )

        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_question_contract_round_trip_preserves_context_and_provenance() -> None:
    curriculum_version_id = uuid4()
    exam_version_id = uuid4()
    node_id = uuid4()
    competency_id = uuid4()
    outcome_id = uuid4()
    prerequisite_id = uuid4()
    source_id = uuid4()

    question = QuestionInput(
        external_code="question-1",
        content_version=2,
        origin_type=QuestionOrigin.GENERATED,
        curriculum_version_id=curriculum_version_id,
        exam_version_id=exam_version_id,
        primary_curriculum_node_id=node_id,
        competency_ids=[competency_id],
        learning_outcome_ids=[outcome_id],
        prerequisite_concept_ids=[prerequisite_id],
        source_ids=[source_id],
        question_type=QuestionType.DESCRIPTIVE,
        stem_text="Explain the reasoning.",
        age_min=14,
        age_max=16,
        grade_year_codes=["grade-9"],
        rubric_json={
            "criteria": [
                {
                    "code": "reasoning",
                    "title": "Reasoning",
                    "max_marks": 4,
                }
            ],
            "total_marks": 4,
        },
    )
    payload = question.model_dump(mode="json")
    loaded = QuestionInput.model_validate(payload)

    assert loaded.curriculum_version_id == curriculum_version_id
    assert loaded.exam_version_id == exam_version_id
    assert loaded.primary_curriculum_node_id == node_id
    assert loaded.competency_ids == [competency_id]
    assert loaded.learning_outcome_ids == [outcome_id]
    assert loaded.prerequisite_concept_ids == [prerequisite_id]
    assert loaded.source_ids == [source_id]
    assert loaded.rubric_json is not None
    assert loaded.rubric_json.criteria[0].code == "reasoning"

    with pytest.raises(ValidationError):
        QuestionInput.model_validate({**payload, "undeclared_context": "must-fail"})


def test_rubric_and_paper_blueprint_are_structurally_validated() -> None:
    with pytest.raises(ValidationError):
        QuestionInput(
            origin_type=QuestionOrigin.GENERATED,
            question_type=QuestionType.DESCRIPTIVE,
            stem_text="Synthetic",
            rubric_json={
                "criteria": [
                    {"code": "a", "title": "A", "max_marks": 2},
                    {"code": "b", "title": "B", "max_marks": 2},
                ],
                "total_marks": 5,
            },
        )

    test = TestDefinitionInput(
        code="paper-x",
        title="Paper X",
        status=TestStatus.DRAFT,
        blueprint_json={
            "mode": PaperMode.CUSTOM,
            "total_question_count": 10,
            "sections": [
                {
                    "code": "section-a",
                    "exact_count": 10,
                    "question_type_counts": {"single_choice": 8, "numerical": 2},
                }
            ],
            "difficulty_distribution": [
                {"key": "easy", "weight": 0.3},
                {"key": "medium", "weight": 0.5},
                {"key": "hard", "weight": 0.2},
            ],
        },
    )
    assert test.blueprint_json.total_question_count == 10
    assert test.blueprint_json.sections[0].exact_count == 10

    with pytest.raises(ValidationError):
        TestDefinitionInput(
            code="invalid-paper",
            title="Invalid",
            blueprint_json={
                "mode": PaperMode.CUSTOM,
                "total_question_count": 10,
                "sections": [{"code": "a", "exact_count": 9}],
                "difficulty_distribution": [
                    {"key": "easy", "weight": 0.8},
                    {"key": "hard", "weight": 0.8},
                ],
            },
        )


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    return config


def _insert_pre_gap_question_graph(database_path: Path) -> dict[str, str]:
    ids = {
        "source": str(uuid4()),
        "question": str(uuid4()),
        "option": str(uuid4()),
        "asset": str(uuid4()),
        "test": str(uuid4()),
        "test_question": str(uuid4()),
    }
    now = datetime.now(UTC).isoformat()
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute(
            """
            INSERT INTO sources (
                id, source_type, title, trust_tier, status, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["source"],
                "official_syllabus",
                "Synthetic source",
                "official_primary",
                "active",
                json.dumps({}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO questions (
                id, external_code, content_version, origin_type,
                curriculum_version_id, exam_version_id, primary_curriculum_node_id,
                question_type, stem_text, stem_latex, solution_text, solution_latex,
                answer_json, difficulty, cognitive_level, status, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["question"],
                "migration-question",
                1,
                "generated",
                None,
                None,
                None,
                "single_choice",
                "Synthetic migration question",
                None,
                "Synthetic solution",
                None,
                json.dumps({"option_key": "A"}),
                2,
                "apply",
                "approved",
                json.dumps({}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO question_options (
                id, question_id, option_key, text, latex, is_correct,
                diagnostic_taxonomy_entry_id, error_code, sequence, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["option"],
                ids["question"],
                "A",
                "Correct",
                None,
                1,
                None,
                None,
                1,
                json.dumps({}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO question_assets (
                id, question_id, asset_type, uri, alt_text, payload_json,
                sequence, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["asset"],
                ids["question"],
                "table",
                None,
                "Synthetic asset",
                json.dumps({"rows": [[1, 2]]}),
                1,
                json.dumps({}),
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO question_sources (question_id, source_id) VALUES (?, ?)",
            (ids["question"], ids["source"]),
        )
        connection.execute(
            """
            INSERT INTO test_definitions (
                id, code, title, curriculum_version_id, exam_version_id,
                blueprint_json, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["test"],
                "migration-test",
                "Migration Test",
                None,
                None,
                json.dumps({"mode": "custom", "total_question_count": 1}),
                "draft",
                json.dumps({}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO test_questions (
                id, test_definition_id, question_id, sequence, section_code,
                marks, negative_marks, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["test_question"],
                ids["test"],
                ids["question"],
                1,
                "section-a",
                4,
                0,
                json.dumps({}),
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return ids


def _assert_question_graph_survives(database_path: Path, ids: dict[str, str]) -> None:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        expected = {
            "questions": ("id", ids["question"]),
            "question_options": ("id", ids["option"]),
            "question_assets": ("id", ids["asset"]),
            "test_definitions": ("id", ids["test"]),
            "test_questions": ("id", ids["test_question"]),
        }
        for table, (column, row_id) in expected.items():
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",
                (row_id,),
            ).fetchone()[0]
            assert count == 1, f"{table} row was not preserved"

        source_link_count = connection.execute(
            "SELECT COUNT(*) FROM question_sources WHERE question_id = ? AND source_id = ?",
            (ids["question"], ids["source"]),
        ).fetchone()[0]
        assert source_link_count == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_populated_sqlite_migration_preserves_question_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "populated-migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    config = _alembic_config()

    command.upgrade(config, "20261001_0002")
    ids = _insert_pre_gap_question_graph(database_path)

    command.upgrade(config, "head")
    _assert_question_graph_survives(database_path, ids)

    command.downgrade(config, "20261001_0002")
    _assert_question_graph_survives(database_path, ids)

    command.upgrade(config, "head")
    _assert_question_graph_survives(database_path, ids)
