from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.jee_advanced.constants import EDUVIJNA_DERIVED_TOPIC_GROUP, MATHEMATICS_SUBJECT
from app.jee_advanced.contracts import PracticeQuestionRef


@dataclass(frozen=True, slots=True)
class SyntheticFixturePool:
    mathematics: tuple[PracticeQuestionRef, ...]
    algebra: tuple[PracticeQuestionRef, ...]
    pool_fingerprint: str


def _build_question(
    *,
    idx: int,
    topic_group: str | None,
    stem_suffix: str,
) -> PracticeQuestionRef:
    qid = f"d12-synthetic-math-{topic_group or 'general'}-{idx:02d}"
    return PracticeQuestionRef(
        question_id=qid,
        subject_code=MATHEMATICS_SUBJECT,
        topic_group=topic_group,
        independently_validated=True,
        solver_audit_id=f"d12-solver-audit-{qid}",
        metadata_json={
            "trust_mode": "synthetic_fixture",
            "stem_preview": f"Synthetic JEE Advanced mathematics item {idx} ({stem_suffix})",
            "day6_validation_id": f"d12-day6-{qid}",
        },
    )


def build_synthetic_fixture_pool(
    *,
    algebra_count: int = 12,
    general_math_count: int = 12,
) -> SyntheticFixturePool:
    """D12-33: labelled synthetic pool — not official 2026/2027 evidence."""

    algebra = tuple(
        _build_question(idx=i, topic_group=EDUVIJNA_DERIVED_TOPIC_GROUP, stem_suffix="algebra")
        for i in range(1, algebra_count + 1)
    )
    mathematics = tuple(
        _build_question(idx=i, topic_group=None, stem_suffix="mathematics")
        for i in range(1, general_math_count + 1)
    )
    payload = {
        "algebra_ids": [q.question_id for q in algebra],
        "mathematics_ids": [q.question_id for q in mathematics],
        "label": "SYNTHETIC_FIXTURE",
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SyntheticFixturePool(
        mathematics=mathematics,
        algebra=algebra,
        pool_fingerprint=fingerprint,
    )
