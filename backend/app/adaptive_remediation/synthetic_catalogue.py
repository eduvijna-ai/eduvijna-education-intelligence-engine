"""D16-04/D16-20 internal original synthetic question catalogue."""

from __future__ import annotations

from dataclasses import dataclass

from app.adaptive_remediation.enums import CognitiveLevel, PracticeStageKind


@dataclass(frozen=True, slots=True)
class SyntheticQuestionRef:
    question_id: str
    concept_code: str
    stage: PracticeStageKind
    cognitive_level: CognitiveLevel
    difficulty_band: str
    question_type: str
    marks: int
    stem_preview: str


def _catalogue_entries() -> list[SyntheticQuestionRef]:
    entries: list[SyntheticQuestionRef] = []
    foundation = [
        ("d16-q-nl-01", "newton-laws", "State the first law in own words (synthetic)."),
        ("d16-q-nl-02", "newton-laws", "Identify action–reaction pair on a block (synthetic)."),
        ("d16-q-nf-01", "normal-force", "Draw normal force on an inclined plane sketch."),
        ("d16-q-nf-02", "normal-force", "Compare normal force on level vs incline."),
        ("d16-q-fr-01", "friction-applications", "Define static vs kinetic friction (synthetic)."),
    ]
    for idx, (qid, concept, stem) in enumerate(foundation, start=1):
        entries.append(
            SyntheticQuestionRef(
                question_id=qid,
                concept_code=concept,
                stage=PracticeStageKind.FOUNDATION,
                cognitive_level=CognitiveLevel.UNDERSTAND if idx % 2 else CognitiveLevel.REMEMBER,
                difficulty_band="foundation",
                question_type="synthetic_open_preview",
                marks=1,
                stem_preview=stem,
            )
        )

    application = [
        (
            "d16-q-ap-01",
            "friction-applications",
            "Pick correct friction direction on accelerating cart.",
        ),
        ("d16-q-ap-02", "friction-formula-selection", "Choose μₛ vs μₖ when object is at rest."),
        (
            "d16-q-ap-03",
            "friction-applications",
            "Compute friction magnitude given N and μ (integer).",
        ),
        (
            "d16-q-ap-04",
            "friction-formula-selection",
            "Match scenario to limiting static friction formula.",
        ),
        (
            "d16-q-ap-05",
            "friction-applications",
            "Explain why friction enables walking (synthetic).",
        ),
    ]
    for idx, (qid, concept, stem) in enumerate(application, start=1):
        entries.append(
            SyntheticQuestionRef(
                question_id=qid,
                concept_code=concept,
                stage=PracticeStageKind.APPLICATION,
                cognitive_level=CognitiveLevel.APPLY if idx < 4 else CognitiveLevel.ANALYZE,
                difficulty_band="application",
                question_type="synthetic_reference",
                marks=2,
                stem_preview=stem,
            )
        )

    retest = [
        (
            "d16-q-rt-01",
            "friction-formula-selection",
            "Fresh item: select formula for block on rough table.",
        ),
        (
            "d16-q-rt-03",
            "friction-formula-selection",
            "Fresh item: justify μ choice under rolling contact.",
        ),
        ("d16-q-rt-05", "friction-formula-selection", "Fresh item: compare friction magnitudes."),
    ]
    for qid, concept, stem in retest:
        entries.append(
            SyntheticQuestionRef(
                question_id=qid,
                concept_code=concept,
                stage=PracticeStageKind.TARGET_RETEST,
                cognitive_level=CognitiveLevel.APPLY,
                difficulty_band="standard",
                question_type="synthetic_reference",
                marks=2,
                stem_preview=stem,
            )
        )
    return entries


_CATALOGUE = tuple(_catalogue_entries())


def internal_synthetic_catalogue() -> tuple[SyntheticQuestionRef, ...]:
    return _CATALOGUE


def select_for_stage(
    stage: PracticeStageKind,
    count: int,
    *,
    excluded_ids: frozenset[str] = frozenset(),
    target_concept_code: str | None = None,
) -> tuple[SyntheticQuestionRef, ...]:
    pool = [q for q in _CATALOGUE if q.stage == stage and q.question_id not in excluded_ids]
    if target_concept_code is not None:
        pool = [q for q in pool if q.concept_code == target_concept_code]
    if count > len(pool):
        return tuple()
    return tuple(pool[:count])


def stage_capacity(
    stage: PracticeStageKind,
    *,
    excluded_ids: frozenset[str] = frozenset(),
    target_concept_code: str | None = None,
) -> int:
    pool = [q for q in _CATALOGUE if q.stage == stage and q.question_id not in excluded_ids]
    if target_concept_code is not None:
        pool = [q for q in pool if q.concept_code == target_concept_code]
    return len(pool)


def retest_items_target_bound(target_concept_code: str) -> bool:
    return stage_capacity(
        PracticeStageKind.TARGET_RETEST,
        target_concept_code=target_concept_code,
    ) >= STAGE_MINIMUM_RET


STAGE_MINIMUM_RET = 1