from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.learner_intelligence.contracts import (
    CreateAttemptRequest,
    FinalizeAttemptRequest,
    RecordResponseRequest,
)
from app.learner_intelligence.enums import AttemptState, EligibilityTrustMode, ResponseKind
from app.learner_intelligence.fixtures import (
    SYNTHETIC_HARNESS_PROOF,
    assessment_content_fingerprint,
    build_two_item_synthetic_assessment,
    seed_synthetic_tenant,
)
from app.learner_intelligence.service import LearnerIntelligenceService


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'd15.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_d15_happy_path_finalize_and_idempotent_replay(tmp_path: Path) -> None:
    session = _session(tmp_path)
    actor = seed_synthetic_tenant(session)
    session.commit()
    items = build_two_item_synthetic_assessment()
    fp = assessment_content_fingerprint(items)
    svc = LearnerIntelligenceService()
    attempt, outcome = svc.create_attempt(
        session,
        CreateAttemptRequest(
            actor=actor,
            trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
            assessment_key="practice-1",
            idempotency_key="idem-1",
            items=items,
            synthetic_harness_proof=SYNTHETIC_HARNESS_PROOF,
        ),
    )
    assert attempt is not None
    assert outcome.eligibility_verdict.value == "eligible"

    views = svc.learner_view_items(session, str(attempt.id))
    assert all("is_correct" not in opt for row in views for opt in row.get("options", []))

    assert svc.record_response(
        session,
        attempt,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["B"],
        ),
    )[0]
    assert svc.record_response(
        session,
        attempt,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=2,
            response_kind=ResponseKind.NUMERIC,
            numeric_value="7",
        ),
    )[0]

    fin = svc.finalize(
        session,
        attempt,
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="fin-1",
            content_binding_fingerprint=fp,
        ),
    )
    assert fin.state == AttemptState.FINALIZED
    assert fin.total_marks == Decimal("8")

    replay = svc.finalize(
        session,
        attempt,
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="fin-1",
            content_binding_fingerprint=fp,
        ),
    )
    assert replay.total_marks == fin.total_marks
    session.close()


def test_d15_draft_before_finalize_no_mastery_events(tmp_path: Path) -> None:
    from sqlalchemy import func, select

    from app.models.learner_intelligence import ScoreEvidenceEvent

    session = _session(tmp_path)
    actor = seed_synthetic_tenant(session)
    session.commit()
    items = build_two_item_synthetic_assessment()
    svc = LearnerIntelligenceService()
    attempt, _ = svc.create_attempt(
        session,
        CreateAttemptRequest(
            actor=actor,
            trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
            assessment_key="practice-2",
            idempotency_key="idem-2",
            items=items,
            synthetic_harness_proof=SYNTHETIC_HARNESS_PROOF,
        ),
    )
    assert attempt is not None
    svc.record_response(
        session,
        attempt,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["B"],
        ),
    )
    count = session.scalar(select(func.count()).select_from(ScoreEvidenceEvent))
    assert count == 0
    session.close()