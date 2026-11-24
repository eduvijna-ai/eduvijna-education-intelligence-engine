"""Map persisted Question rows to Day6 CanonicalAssessmentItem (explicit bridge)."""

from __future__ import annotations

from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    CognitiveDemandEvidence,
    DifficultyEvidence,
    QuestionOptionInput,
)
from app.models import Question


def question_to_canonical_assessment_item(
    question: Question,
    *,
    curriculum_version_id: str,
    learning_outcome_id: str,
    competency_code: str,
    organization_id: str,
    institution_id: str,
) -> CanonicalAssessmentItem:
    meta = dict(question.metadata_json or {})
    options = [
        QuestionOptionInput(
            option_key=opt.option_key,
            text=opt.text,
            is_correct=bool(opt.is_correct),
        )
        for opt in sorted(question.options, key=lambda row: row.sequence)
    ]
    return CanonicalAssessmentItem(
        item_id=str(question.id),
        stem_text=question.stem_text,
        question_type="single_choice",
        options=options,
        declared_cognitive_level="Apply",
        competency_codes=[competency_code],
        learning_outcome_ids=[learning_outcome_id],
        curriculum_version_id=curriculum_version_id,
        grade_year_code="ug-year-1",
        medium_code=str(meta.get("medium_code") or "english"),
        subject_code="mathematics",
        declared_difficulty=2,
        difficulty_evidence=DifficultyEvidence(
            cognitive_demand_band=2,
            step_count=1,
            computation_load=2,
            language_load=1,
        ),
        cognitive_demand_evidence=CognitiveDemandEvidence(application_required=True),
        age_min=17,
        age_max=20,
        answer_metadata_present=bool(question.answer_json),
        institution_id=institution_id,
        metadata_json={
            "d13_synthetic_fixture": True,
            "organization_id": organization_id,
            "cuet_subject_code": meta.get("subject_code"),
            "not_official_cuet_item": True,
        },
    )