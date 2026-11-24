"""D16-16..D16-23 practice allocation and blueprint planning."""

from __future__ import annotations

from app.adaptive_remediation.contracts import PracticeStageBlueprint
from app.adaptive_remediation.enums import PracticeStageKind
from app.adaptive_remediation.synthetic_catalogue import (
    select_for_stage,
    stage_capacity,
)
from app.adaptive_remediation.synthetic_fixture import AUTHORITATIVE_TARGET_CONCEPT
from app.adaptive_remediation.validation import require_strict_positive_int

STAGE_MINIMUM = 1
PREFERRED_RATIOS = (0.4, 0.4, 0.2)


def validate_strict_positive_int(value: object) -> int | None:
    return require_strict_positive_int(value)


def _stage_capacities(excluded_question_ids: frozenset[str]) -> dict[PracticeStageKind, int]:
    retest_target = AUTHORITATIVE_TARGET_CONCEPT
    return {
        PracticeStageKind.FOUNDATION: stage_capacity(
            PracticeStageKind.FOUNDATION,
            excluded_ids=excluded_question_ids,
        ),
        PracticeStageKind.APPLICATION: stage_capacity(
            PracticeStageKind.APPLICATION,
            excluded_ids=excluded_question_ids,
        ),
        PracticeStageKind.TARGET_RETEST: stage_capacity(
            PracticeStageKind.TARGET_RETEST,
            excluded_ids=excluded_question_ids,
            target_concept_code=retest_target,
        ),
    }


def _enumerate_feasible_splits(
    requested: int,
    *,
    excluded_question_ids: frozenset[str],
) -> list[tuple[int, int, int]]:
    if requested < STAGE_MINIMUM * 3:
        return []
    caps = _stage_capacities(excluded_question_ids)
    f_cap = caps[PracticeStageKind.FOUNDATION]
    a_cap = caps[PracticeStageKind.APPLICATION]
    r_cap = caps[PracticeStageKind.TARGET_RETEST]
    splits: list[tuple[int, int, int]] = []
    for foundation in range(STAGE_MINIMUM, min(requested, f_cap) + 1):
        for application in range(STAGE_MINIMUM, min(requested - foundation, a_cap) + 1):
            retest = requested - foundation - application
            if retest < STAGE_MINIMUM or retest > r_cap:
                continue
            splits.append((foundation, application, retest))
    return splits


def _pick_split(
    requested: int,
    *,
    excluded_question_ids: frozenset[str],
) -> tuple[int, int, int] | None:
    splits = _enumerate_feasible_splits(requested, excluded_question_ids=excluded_question_ids)
    if not splits:
        return None

    def score(split: tuple[int, int, int]) -> tuple[float, int, int, int]:
        foundation, application, retest = split
        target_f = requested * PREFERRED_RATIOS[0]
        target_a = requested * PREFERRED_RATIOS[1]
        target_r = requested * PREFERRED_RATIOS[2]
        deviation = (
            abs(foundation - target_f)
            + abs(application - target_a)
            + abs(retest - target_r)
        )
        balance_penalty = abs(foundation - application) + abs(application - retest)
        return (deviation, balance_penalty, foundation, application)

    return min(splits, key=score)


def allocate_stage_counts(
    requested: object,
    *,
    excluded_question_ids: frozenset[str] = frozenset(),
) -> tuple[int, int, int] | None:
    value = validate_strict_positive_int(requested)
    if value is None:
        return None
    caps = _stage_capacities(excluded_question_ids)
    total_capacity = sum(caps.values())
    if value > total_capacity:
        return None
    return _pick_split(value, excluded_question_ids=excluded_question_ids)


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
        retest_target = (
            AUTHORITATIVE_TARGET_CONCEPT if stage == PracticeStageKind.TARGET_RETEST else None
        )
        selected = select_for_stage(
            stage,
            count,
            excluded_ids=frozenset(used),
            target_concept_code=retest_target,
        )
        if len(selected) < count:
            return None
        for item in selected:
            used.add(item.question_id)
        concept_codes = tuple(dict.fromkeys(item.concept_code for item in selected))
        item_meta = tuple(
            {
                "question_id": item.question_id,
                "concept_code": item.concept_code,
                "cognitive_level": item.cognitive_level.value,
                "question_type": item.question_type,
                "marks": item.marks,
                "difficulty_band": item.difficulty_band,
            }
            for item in selected
        )
        first = selected[0]
        if first.difficulty_band not in ("foundation", "standard", "application"):
            return None
        stages.append(
            PracticeStageBlueprint(
                stage=stage,
                concept_codes=concept_codes,
                cognitive_level=first.cognitive_level,
                difficulty_band=first.difficulty_band,
                question_type="synthetic_reference",
                marks_per_item=first.marks,
                planned_count=count,
                selected_synthetic_ids=tuple(q.question_id for q in selected),
                metadata_json={
                    "synthetic_only": True,
                    "no_validated_mcq": True,
                    "per_item": item_meta,
                },
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