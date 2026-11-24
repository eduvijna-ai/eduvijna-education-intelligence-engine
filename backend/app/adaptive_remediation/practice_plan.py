"""D16-16..D16-23 practice allocation and blueprint planning."""

from __future__ import annotations

from app.adaptive_remediation.contracts import PracticeStageBlueprint
from app.adaptive_remediation.enums import CognitiveLevel, PracticeStageKind
from app.adaptive_remediation.synthetic_catalogue import (
    internal_synthetic_catalogue,
    select_for_stage,
)


def _stage_weights(total: int) -> tuple[int, int, int]:
    """Deterministic 40/40/20 illustration — not an official rule."""
    if total < 3:
        return total, 0, 0
    foundation = max(1, (total * 4) // 10)
    application = max(1, (total * 4) // 10)
    retest = max(1, total - foundation - application)
    while foundation + application + retest > total:
        if retest > 1:
            retest -= 1
        elif application > 1:
            application -= 1
        elif foundation > 1:
            foundation -= 1
        else:
            break
    if foundation + application + retest < total:
        retest += total - (foundation + application + retest)
    return foundation, application, retest


def allocate_stage_counts(requested: int) -> tuple[int, int, int] | None:
    if requested <= 0 or not isinstance(requested, int):
        return None
    if requested > len(internal_synthetic_catalogue()):
        return None
    return _stage_weights(requested)


def build_stage_blueprints(
    requested_count: int,
    *,
    concept_codes: tuple[str, ...],
    excluded_question_ids: frozenset[str] = frozenset(),
) -> tuple[PracticeStageBlueprint, ...] | None:
    split = allocate_stage_counts(requested_count)
    if split is None:
        return None
    foundation_n, application_n, retest_n = split
    stages: list[PracticeStageBlueprint] = []
    used: set[str] = set(excluded_question_ids)

    for stage, count, level, band in (
        (PracticeStageKind.FOUNDATION, foundation_n, CognitiveLevel.UNDERSTAND, "foundation"),
        (PracticeStageKind.APPLICATION, application_n, CognitiveLevel.APPLY, "application"),
        (PracticeStageKind.TARGET_RETEST, retest_n, CognitiveLevel.APPLY, "standard"),
    ):
        if count <= 0:
            continue
        selected = select_for_stage(stage, count, excluded_ids=frozenset(used))
        if len(selected) < count:
            return None
        for item in selected:
            used.add(item.question_id)
        stages.append(
            PracticeStageBlueprint(
                stage=stage,
                concept_codes=concept_codes or tuple(item.concept_code for item in selected),
                cognitive_level=level,
                difficulty_band=band,
                question_type="mcq_single",
                marks_per_item=selected[0].marks,
                planned_count=count,
                selected_synthetic_ids=tuple(q.question_id for q in selected),
            )
        )

    planned = sum(s.planned_count for s in stages)
    if planned != requested_count:
        return None
    return tuple(stages)


def count_conservation_ok(stages: tuple[PracticeStageBlueprint, ...], requested: int) -> bool:
    planned = sum(s.planned_count for s in stages)
    selected = sum(len(s.selected_synthetic_ids) for s in stages)
    all_ids = [qid for s in stages for qid in s.selected_synthetic_ids]
    return planned == requested and selected == requested and len(all_ids) == len(set(all_ids))
