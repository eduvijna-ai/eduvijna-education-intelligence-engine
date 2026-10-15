from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    CognitiveDemandEvidence,
    DifficultyEvidence,
    QuestionOptionInput,
)
from app.orchestration.contracts import DraftQuestionItem, ResolvedScope


def _optional_model[ModelT: BaseModel](model_cls: type[ModelT], raw: Any) -> ModelT | None:
    if raw is None or not isinstance(raw, dict):
        return None
    return model_cls.model_validate(raw)


def draft_to_canonical(
    draft: DraftQuestionItem,
    scope: ResolvedScope,
    *,
    request_marks: float | None,
) -> CanonicalAssessmentItem:
    meta = dict(draft.metadata_json or {})
    has_correct = any(option.is_correct for option in draft.options)
    return CanonicalAssessmentItem(
        item_id=draft.item_id,
        stem_text=draft.stem_text,
        question_type=draft.question_type,
        options=[
            QuestionOptionInput(
                option_key=opt.option_key, text=opt.text, is_correct=opt.is_correct
            )
            for opt in draft.options
        ],
        declared_cognitive_level=draft.declared_cognitive_level,
        competency_codes=draft.competency_codes,
        learning_outcome_ids=draft.learning_outcome_ids,
        curriculum_version_id=scope.curriculum_version_id,
        grade_year_code=scope.grade_year_code,
        medium_code=scope.medium_code,
        subject_code=scope.subject_code,
        declared_difficulty=draft.declared_difficulty,
        difficulty_evidence=_optional_model(DifficultyEvidence, meta.get("difficulty_evidence")),
        cognitive_demand_evidence=_optional_model(
            CognitiveDemandEvidence, meta.get("cognitive_demand_evidence")
        ),
        age_min=meta.get("age_min") if isinstance(meta.get("age_min"), int) else None,
        age_max=meta.get("age_max") if isinstance(meta.get("age_max"), int) else None,
        institution_id=scope.institution_id,
        answer_metadata_present=has_correct,
        content_text_for_safety=meta.get("content_text_for_safety")
        if isinstance(meta.get("content_text_for_safety"), str)
        else None,
        metadata_json={
            k: v
            for k, v in meta.items()
            if k
            not in {
                "difficulty_evidence",
                "cognitive_demand_evidence",
                "age_min",
                "age_max",
                "content_text_for_safety",
            }
        }
        | {
            "marks": request_marks if request_marks is not None else draft.marks,
        },
    )
