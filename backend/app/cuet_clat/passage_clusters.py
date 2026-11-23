from __future__ import annotations

from app.cuet_clat.contracts import PassageCluster, PracticeQuestionRef
from app.cuet_clat.copyright_passages import passage_for_section


def build_passage_clusters(
    section_code: str,
    questions: list[PracticeQuestionRef],
    *,
    questions_per_passage: int = 4,
) -> list[PassageCluster]:
    """D13-19: group ordered questions under originally authored parent passages."""

    clusters: list[PassageCluster] = []
    chunk: list[PracticeQuestionRef] = []
    passage_index = 0

    for q in questions:
        chunk.append(q)
        if len(chunk) >= questions_per_passage:
            passage_id, text = passage_for_section(section_code, index=passage_index)
            clusters.append(
                PassageCluster(
                    passage_id=passage_id,
                    passage_text=text,
                    section_code=section_code,
                    authorship="eduvijna_original_demonstration",
                    question_ids=[c.question_id for c in chunk],
                    metadata_json={"cluster_order": passage_index},
                )
            )
            for c in chunk:
                c.passage_id = passage_id
            chunk = []
            passage_index += 1

    if chunk:
        passage_id, text = passage_for_section(section_code, index=passage_index)
        clusters.append(
            PassageCluster(
                passage_id=passage_id,
                passage_text=text,
                section_code=section_code,
                authorship="eduvijna_original_demonstration",
                question_ids=[c.question_id for c in chunk],
            )
        )
        for c in chunk:
            c.passage_id = passage_id

    return clusters