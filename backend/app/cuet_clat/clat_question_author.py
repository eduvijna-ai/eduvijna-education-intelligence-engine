"""F03-B: assemble authored CLAT passage questions into clusters."""

from __future__ import annotations

from app.cuet_clat.clat_original_passages import load_official_f03b_passages
from app.cuet_clat.clat_passage_contracts import (
    CLAT_ORIGINAL_SOURCE_MODE,
    ClatOriginalPassage,
    authored_to_practice_ref,
)
from app.cuet_clat.contracts import PassageCluster, PracticeQuestionRef


def build_passage_cluster(passage: ClatOriginalPassage) -> PassageCluster:
    question_ids = [q.question_id for q in passage.questions]
    return PassageCluster(
        passage_id=passage.passage_id,
        passage_text=passage.passage_text,
        section_code=passage.section_code,
        authorship=CLAT_ORIGINAL_SOURCE_MODE,
        question_ids=question_ids,
        metadata_json={
            "passage_fingerprint": passage.passage_fingerprint(),
            "source_mode": CLAT_ORIGINAL_SOURCE_MODE,
        },
    )


def load_authored_passage_fixtures() -> list[ClatOriginalPassage]:
    return list(load_official_f03b_passages())


def practice_refs_for_passage(passage: ClatOriginalPassage) -> list[PracticeQuestionRef]:
    return [authored_to_practice_ref(q) for q in passage.questions]