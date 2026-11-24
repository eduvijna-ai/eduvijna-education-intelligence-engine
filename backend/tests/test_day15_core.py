from decimal import Decimal
from pathlib import Path

from app.learner_intelligence.contracts import FinalizeAttemptRequest, RecordResponseRequest
from app.learner_intelligence.enums import AttemptState, ResponseKind
from app.learner_intelligence.fixtures import (
    assessment_content_fingerprint,
    build_harness_attempt_request,
)
from app.learner_intelligence.harness_runtime import (
    ephemeral_file_harness,
    isolated_harness_session,
)
from app.learner_intelligence.service import LearnerIntelligenceService


def test_d15_happy_path_finalize_and_idempotent_replay(tmp_path: Path) -> None:
    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as (session, _binding, actor):
        items = build_harness_attempt_request(
            actor, assessment_key="practice-1", idempotency_key="idem-1"
        )
        fp = assessment_content_fingerprint(items.items)
        svc = LearnerIntelligenceService()
        attempt, outcome = svc.create_attempt(session, items)
        assert attempt is not None
        assert outcome.eligibility_verdict.value == "eligible"

        views, view_issues = svc.learner_view_items(session, actor, str(attempt.id))
        assert not view_issues
        assert "content_fingerprint" not in "".join(str(v) for v in views)

        assert svc.record_response(
            session,
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
            FinalizeAttemptRequest(
                actor=actor,
                attempt_id=str(attempt.id),
                idempotency_key="fin-1",
                content_binding_fingerprint=fp,
            ),
        )
        assert fin.state == AttemptState.FINALIZED
        assert fin.total_marks == Decimal("8")
        assert fin.max_marks == Decimal("8")

        replay = svc.finalize(
            session,
            FinalizeAttemptRequest(
                actor=actor,
                attempt_id=str(attempt.id),
                idempotency_key="fin-1",
                content_binding_fingerprint=fp,
            ),
        )
        assert replay.total_marks == fin.total_marks


def test_d15_missing_item_scores_blank_contributes_max(tmp_path: Path) -> None:
    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as (session, _binding, actor):
        create_req = build_harness_attempt_request(
            actor, assessment_key="practice-partial", idempotency_key="idem-partial"
        )
        fp = assessment_content_fingerprint(create_req.items)
        svc = LearnerIntelligenceService()
        attempt, _ = svc.create_attempt(session, create_req)
        assert attempt is not None
        svc.record_response(
            session,
            RecordResponseRequest(
                actor=actor,
                attempt_id=str(attempt.id),
                item_sequence=1,
                response_kind=ResponseKind.SINGLE_CHOICE,
                selected_option_keys=["B"],
            ),
        )
        fin = svc.finalize(
            session,
            FinalizeAttemptRequest(
                actor=actor,
                attempt_id=str(attempt.id),
                idempotency_key="fin-partial",
                content_binding_fingerprint=fp,
            ),
        )
        assert fin.total_marks == Decimal("4")
        assert fin.max_marks == Decimal("8")


def test_d15_draft_before_finalize_no_mastery_events(tmp_path: Path) -> None:
    from sqlalchemy import func, select

    from app.models.learner_intelligence import ScoreEvidenceEvent

    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as (session, _binding, actor):
        svc = LearnerIntelligenceService()
        attempt, _ = svc.create_attempt(
            session,
            build_harness_attempt_request(
                actor,
                assessment_key="practice-2",
                idempotency_key="idem-2",
            ),
        )
        assert attempt is not None
        svc.record_response(
            session,
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