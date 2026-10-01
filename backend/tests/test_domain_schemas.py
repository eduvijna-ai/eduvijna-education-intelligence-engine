from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import (
    BlueprintRuleType,
    DiagnosticCategory,
    PolicyScopeType,
    QuestionOrigin,
    QuestionType,
    SourceType,
)
from app.schemas.domain import (
    ConceptPrerequisiteInput,
    DiagnosticTaxonomyInput,
    ExamBlueprintRuleInput,
    PolicyRuleInput,
    QuestionInput,
    QuestionOptionInput,
    SourceInput,
)


def test_source_enum_serializes_to_stable_value() -> None:
    source = SourceInput(source_type=SourceType.OFFICIAL_SYLLABUS, title="Synthetic syllabus")
    assert source.model_dump(mode="json")["source_type"] == "official_syllabus"


def test_blueprint_supports_exact_and_range_counts() -> None:
    exact = ExamBlueprintRuleInput(
        rule_type=BlueprintRuleType.QUESTION_COUNT,
        exact_count=25,
    )
    ranged = ExamBlueprintRuleInput(
        rule_type=BlueprintRuleType.QUESTION_COUNT,
        min_count=22,
        max_count=26,
    )
    assert exact.exact_count == 25
    assert ranged.min_count == 22
    assert ranged.max_count == 26


def test_blueprint_rejects_invalid_range() -> None:
    with pytest.raises(ValidationError):
        ExamBlueprintRuleInput(
            rule_type=BlueprintRuleType.QUESTION_COUNT,
            min_count=30,
            max_count=20,
        )


def test_prerequisite_rejects_self_reference() -> None:
    concept_id = uuid4()
    with pytest.raises(ValidationError):
        ConceptPrerequisiteInput(
            prerequisite_concept_id=concept_id,
            target_concept_id=concept_id,
        )


def test_single_choice_requires_exactly_one_correct_option() -> None:
    with pytest.raises(ValidationError):
        QuestionInput(
            origin_type=QuestionOrigin.GENERATED,
            question_type=QuestionType.SINGLE_CHOICE,
            stem_text="Synthetic question",
            options=[
                QuestionOptionInput(option_key="A", text="A", is_correct=True),
                QuestionOptionInput(option_key="B", text="B", is_correct=True),
            ],
        )


def test_duplicate_option_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        QuestionInput(
            origin_type=QuestionOrigin.GENERATED,
            question_type=QuestionType.SINGLE_CHOICE,
            stem_text="Synthetic question",
            options=[
                QuestionOptionInput(option_key="A", text="A", is_correct=True),
                QuestionOptionInput(option_key="A", text="B"),
            ],
        )


def test_question_difficulty_scale_is_enforced() -> None:
    with pytest.raises(ValidationError):
        QuestionInput(
            origin_type=QuestionOrigin.GENERATED,
            question_type=QuestionType.DESCRIPTIVE,
            stem_text="Synthetic question",
            difficulty=6,
        )


def test_diagnostic_and_policy_schemas_are_configurable() -> None:
    diagnostic = DiagnosticTaxonomyInput(
        code="FORMULA_SELECTION_ERROR",
        name="Formula selection error",
        category=DiagnosticCategory.FORMULA_KNOWLEDGE,
    )
    policy = PolicyRuleInput(
        scope_type=PolicyScopeType.INSTITUTION,
        scope_code="school-a",
        policy_key="question.difficulty.max",
        value_json={"value": 4},
    )
    assert diagnostic.code == "FORMULA_SELECTION_ERROR"
    assert policy.priority == 0
