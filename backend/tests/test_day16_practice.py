from app.adaptive_remediation.practice_plan import (
    allocate_stage_counts,
    build_stage_blueprints,
    count_conservation_ok,
    validate_strict_positive_int,
)
from app.adaptive_remediation.synthetic_fixture import INTERNAL_HISTORY


def test_strict_int_rejects_bool_and_float() -> None:
    assert validate_strict_positive_int(True) is None
    assert validate_strict_positive_int(10.5) is None
    assert validate_strict_positive_int(10) == 10


def test_exact_counts_5_10_15_with_exclusions() -> None:
    excluded = frozenset(INTERNAL_HISTORY.excluded_question_ids)
    for n in (5, 10):
        split = allocate_stage_counts(n, excluded_question_ids=excluded)
        assert split is not None
        assert sum(split) == n
    assert allocate_stage_counts(15, excluded_question_ids=excluded) is None
    assert allocate_stage_counts(20, excluded_question_ids=excluded) is None
    assert allocate_stage_counts(2, excluded_question_ids=excluded) is None


def test_no_duplicate_selection_and_metadata_bound() -> None:
    excluded = frozenset(INTERNAL_HISTORY.excluded_question_ids)
    stages = build_stage_blueprints(10, excluded_question_ids=excluded)
    assert stages is not None
    assert count_conservation_ok(stages, 10)
    for stage in stages:
        assert stage.planned_count == len(stage.selected_synthetic_ids)
        assert stage.question_type == "mcq_single"