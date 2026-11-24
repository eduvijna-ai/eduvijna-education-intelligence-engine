from app.adaptive_remediation.practice_plan import (
    allocate_stage_counts,
    build_stage_blueprints,
    count_conservation_ok,
)


def test_exact_counts_5_10_15_20() -> None:
    for n in (5, 10, 15):
        split = allocate_stage_counts(n)
        assert split is not None
        assert sum(split) == n


def test_impossible_budget_returns_none() -> None:
    assert allocate_stage_counts(0) is None
    assert allocate_stage_counts(100) is None


def test_no_duplicate_selection() -> None:
    stages = build_stage_blueprints(10, concept_codes=("friction-applications",))
    assert stages is not None
    assert count_conservation_ok(stages, 10)
