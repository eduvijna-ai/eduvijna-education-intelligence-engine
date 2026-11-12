from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.jee_advanced.constants import (
    EDUVIJNA_DERIVED_TOPIC_GROUP,
    MATHEMATICS_SUBJECT,
    OFFICIAL_SUBJECTS,
)
from app.jee_advanced.contracts import PracticeQuestionRef

ITEMS_PER_SUBJECT_POOL = 12


@dataclass(frozen=True, slots=True)
class SyntheticFixturePool:
    by_subject: dict[str, tuple[PracticeQuestionRef, ...]]
    algebra: tuple[PracticeQuestionRef, ...]
    pool_fingerprint: str

    @property
    def mathematics(self) -> tuple[PracticeQuestionRef, ...]:
        return self.by_subject[MATHEMATICS_SUBJECT]


def _build_pcm_question(
    *,
    subject_code: str,
    idx: int,
    question_type: str,
    topic_group: str | None = None,
) -> PracticeQuestionRef:
    qid = f"d12-synthetic-{subject_code}-{question_type}-{idx:02d}"
    return PracticeQuestionRef(
        question_id=qid,
        subject_code=subject_code,
        topic_group=topic_group,
        independently_validated=True,
        solver_audit_id=f"d12-solver-audit-{qid}",
        metadata_json={
            "trust_mode": "synthetic_fixture",
            "demonstration_only": True,
            "question_type": question_type,
            "stem_preview": f"Synthetic JEE Advanced {subject_code} {question_type} {idx}",
            "day6_validation_id": f"d12-day6-{qid}",
        },
    )


def build_synthetic_fixture_pool(
    *,
    items_per_subject: int = ITEMS_PER_SUBJECT_POOL,
) -> SyntheticFixturePool:
    """D12-33: PCM-labelled synthetic pool — not official 2026/2027 evidence."""

    types = ("mcq_single", "mcq_multi", "numerical")
    by_subject: dict[str, tuple[PracticeQuestionRef, ...]] = {}
    for subject in OFFICIAL_SUBJECTS:
        items: list[PracticeQuestionRef] = []
        for idx in range(1, items_per_subject + 1):
            qtype = types[(idx - 1) % len(types)]
            topic = None
            if subject == MATHEMATICS_SUBJECT and idx <= 6:
                topic = EDUVIJNA_DERIVED_TOPIC_GROUP if idx % 2 == 0 else None
            items.append(
                _build_pcm_question(
                    subject_code=subject,
                    idx=idx,
                    question_type=qtype,
                    topic_group=topic,
                )
            )
        by_subject[subject] = tuple(items)

    math_items = by_subject[MATHEMATICS_SUBJECT]
    algebra = tuple(q for q in math_items if q.topic_group == EDUVIJNA_DERIVED_TOPIC_GROUP)
    extra_algebra = [
        _build_pcm_question(
            subject_code=MATHEMATICS_SUBJECT,
            idx=200 + i,
            question_type="mcq_single",
            topic_group=EDUVIJNA_DERIVED_TOPIC_GROUP,
        )
        for i in range(1, max(1, 12 - len(algebra)) + 1)
    ]
    algebra = algebra + tuple(extra_algebra)

    payload = {
        "subjects": {k: [q.question_id for q in v] for k, v in by_subject.items()},
        "label": "SYNTHETIC_FIXTURE_PCM",
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SyntheticFixturePool(
        by_subject=by_subject,
        algebra=algebra,
        pool_fingerprint=fingerprint,
    )
