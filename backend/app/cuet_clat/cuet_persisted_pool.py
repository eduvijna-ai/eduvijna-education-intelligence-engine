"""Seed persisted, solver-checked, Day6-validated CUET math questions (synthetic only)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.cuet_clat.constants import CUET_MARK_CORRECT, CUET_MARK_INCORRECT, MATHEMATICS_DOMAIN
from app.cuet_clat.cuet_fixture_curriculum import seed_cuet_math_fixture_curriculum
from app.cuet_clat.cuet_math_author import OPTION_KEYS, generate_cuet_math_authored_items
from app.cuet_clat.cuet_math_solver import solver_confirms_author
from app.cuet_clat.cuet_validation_bridge import run_day6_validation_for_question
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.models import Question, QuestionOption
from app.models.enums import QuestionOrigin, QuestionStatus, QuestionType


def seed_validated_cuet_math_questions(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    exam_version_id: str | None = None,
    pool_size: int = 50,
    medium_code: str = "english",
    academic_year: str = "2026",
) -> list[str]:
    """Author, solver-verify, Day6-validate and APPROVE synthetic CUET math rows."""

    ctx = seed_cuet_math_fixture_curriculum(session)
    cuet_ver, _ = ensure_synthetic_demo_versions(session)
    resolved_exam_version_id = exam_version_id or str(cuet_ver.id)

    created_ids: list[str] = []
    for authored in generate_cuet_math_authored_items(count=pool_size):
        ok_solver, evidence = solver_confirms_author(authored)
        if not ok_solver or evidence is None:
            continue

        correct_key = evidence.answer_key
        question = Question(
            external_code=authored.external_code,
            origin_type=QuestionOrigin.GENERATED.value,
            exam_version_id=resolved_exam_version_id,
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text=authored.stem_text,
            answer_json={"option_key": correct_key},
            solution_text="; ".join(authored.solution_steps),
            status=QuestionStatus.DRAFT.value,
            metadata_json={
                "d13_synthetic_fixture": True,
                "not_official_cuet_item": True,
                "organization_id": organization_id,
                "institution_id": institution_id,
                "subject_code": MATHEMATICS_DOMAIN,
                "topic_code": authored.topic_code,
                "medium_code": medium_code,
                "academic_year": academic_year,
                "marks_correct": CUET_MARK_CORRECT,
                "marks_incorrect": CUET_MARK_INCORRECT,
            },
        )
        for seq, key in enumerate(OPTION_KEYS):
            text = authored.option_text_by_key[key]
            question.options.append(
                QuestionOption(
                    option_key=key,
                    text=text,
                    is_correct=key == correct_key,
                    sequence=seq + 1,
                )
            )
        session.add(question)
        session.flush()

        validated, _reason = run_day6_validation_for_question(
            session,
            question=question,
            curriculum_version_id=ctx["curriculum_version_id"],
            learning_outcome_id=ctx["learning_outcome_id"],
            competency_code=ctx["competency_code"],
            organization_id=organization_id,
            institution_id=institution_id,
            evidence=evidence,
        )
        if not validated:
            session.delete(question)
            session.flush()
            continue
        question.status = QuestionStatus.APPROVED.value
        session.flush()
        created_ids.append(str(question.id))

    session.commit()
    return created_ids