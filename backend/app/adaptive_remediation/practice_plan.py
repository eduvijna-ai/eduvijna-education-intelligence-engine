"""D16-16..D16-23 practice allocation and blueprint planning."""

from __future__ import annotations

from app.adaptive_remediation.contracts import PracticeStageBlueprint
from app.adaptive_remediation.enums import PracticeStageKind
from app.adaptive_remediation.synthetic_catalogue import (
    select_for_stage,
    stage_capacity,
)


def validate_strict_positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def _feasible_split(
    requested: int,
    *,
    excluded_question_ids: frozenset[str],
) -> tuple[int, int, int] | None:
    """40/40/20 split when feasible; each stage >=1 when requested >= 3."""
    if requested < 3:
        return None
    foundation = max(1, (requested * 4) // 10)
    application = max(1, (requested * 4) // 10)
    retest = max(1, requested - foundation - application)
    while foundation + application + retest > requested:
        if retest > 1:
            retest -= 1
        elif application > 1:
            application -= 1
        elif foundation > 1:
            foundation -= 1
        else:
            return None
    if foundation + application + retest < requested:
        retest += requested - (foundation + application + retest)
    for stage, count in (
        (PracticeStageKind.FOUNDATION, foundation),
        (PracticeStageKind.APPLICATION, application),
        (PracticeStageKind.TARGET_RETEST, retest),
    ):
        available = stage_capacity(stage, excluded_ids=excluded_question_ids)
        if count > available:
            return None
    return foundation, application, retest


def allocate_stage_counts(
    requested: object,
    *,
    excluded_question_ids: frozenset[str] = frozenset(),
) -> tuple[int, int, int] | None:
    value = validate_strict_positive_int(requested)
    if value is None:
        return None
    total_capacity = sum(
        stage_capacity(stage, excluded_ids=excluded_question_ids)
        for stage in (
            PracticeStageKind.FOUNDATION,
            PracticeStageKind.APPLICATION,
            PracticeStageKind.TARGET_RETEST,
        )
    )
    if value > total_capacity:
        return None
    return _feasible_split(value, excluded_question_ids=excluded_question_ids)


def build_stage_blueprints(
    requested_count: object,
    *,
    excluded_question_ids: frozenset[str] = frozenset(),
) -> tuple[PracticeStageBlueprint, ...] | None:
    split = allocate_stage_counts(requested_count, excluded_question_ids=excluded_question_ids)
    if split is None:
        return None
    value = validate_strict_positive_int(requested_count)
    assert value is not None
    foundation_n, application_n, retest_n = split
    stages: list[PracticeStageBlueprint] = []
    used: set[str] = set(excluded_question_ids)

    for stage, count in (
        (PracticeStageKind.FOUNDATION, foundation_n),
        (PracticeStageKind.APPLICATION, application_n),
        (PracticeStageKind.TARGET_RETEST, retest_n),
    ):
        if count <= 0:
            return None
        selected = select_for_stage(stage, count, excluded_ids=frozenset(used))
        if len(selected) < count:
            return None
        for item in selected:
            used.add(item.question_id)
        concept_codes = tuple(dict.fromkeys(item.concept_code for item in selected))
        first = selected[0]
        if first.difficulty_band not in ("foundation", "standard", "application"):
            return None
        stages.append(
            PracticeStageBlueprint(
                stage=stage,
                concept_codes=concept_codes,
                cognitive_level=first.cognitive_level,
                difficulty_band=first.difficulty_band,
                question_type=first.question_type,
                marks_per_item=first.marks,
                planned_count=count,
                selected_synthetic_ids=tuple(q.question_id for q in selected),
            )
        )

    if sum(s.planned_count for s in stages) != value:
        return None
    return tuple(stages)


def count_conservation_ok(stages: tuple[PracticeStageBlueprint, ...], requested: int) -> bool:
    planned = sum(s.planned_count for s in stages)
    selected = sum(len(s.selected_synthetic_ids) for s in stages)
    all_ids = [qid for s in stages for qid in s.selected_synthetic_ids]
    per_stage_ok = all(s.planned_count == len(s.selected_synthetic_ids) for s in stages)
    return (
        planned == requested
        and selected == requested
        and len(all_ids) == len(set(all_ids))
        and per_stage_ok
    )
