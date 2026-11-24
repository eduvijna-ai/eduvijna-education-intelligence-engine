from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.learner_intelligence.containment import CONTAINMENT_ACTIVE, runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import (
    FinalizeAttemptRequest,
    RecordResponseRequest,
    TrustedActorContext,
)
from app.learner_intelligence.diagnostics import record_diagnostic_events
from app.learner_intelligence.enums import AttemptState, IssueCode, ResponseKind, ScoringVerdict
from app.learner_intelligence.finalization import FinalizationError, finalize_attempt
from app.learner_intelligence.fixtures import build_harness_attempt_request
from app.learner_intelligence.harness import build_two_item_catalog_items
from app.learner_intelligence.lifecycle import (
    LifecycleBlockedError,
    transition_attempt,
    validate_and_store_response,
)
from app.learner_intelligence.mastery import apply_mastery_update
from app.learner_intelligence.query import read_diagnostic_events
from app.learner_intelligence.scoring import score_item_response
from app.learner_intelligence.service import LearnerIntelligenceService
from app.models import Institution, Learner, Organization
from app.models.learner_intelligence import AssessmentAttempt, ScoreEvidenceEvent


def test_containment_flags_fail_closed() -> None:
    assert CONTAINMENT_ACTIVE is True
    assert runtime_learner_db_io_allowed() is False


def _session_with_pending_org(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'pending.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Organization(code="pending", name="Pending", active=True))
    session.flush()
    return session


def test_blocked_paths_do_not_commit_pending_caller_work(tmp_path: Path) -> None:
    session = _session_with_pending_org(tmp_path)
    try:
        actor = TrustedActorContext(organization_id="o", institution_id="i", learner_id="l")
        svc = LearnerIntelligenceService()
        _, outcome = svc.create_attempt(
            session,
            build_harness_attempt_request(actor, assessment_key="p", idempotency_key="p1"),
        )
        assert IssueCode.NOT_READY in outcome.issue_codes
        session.rollback()
        count = session.scalar(select(func.count()).select_from(Organization))
        assert count == 0
    finally:
        session.close()


def test_direct_helpers_no_db_writes(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'helpers.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(code="o1", name="O", active=True)
        session.add(org)
        session.flush()
        inst = Institution(organization_id=str(org.id), code="i", name="I", active=True)
        session.add(inst)
        session.flush()
        learner = Learner(
            institution_id=str(inst.id),
            external_code="l",
            display_name="L",
            active=True,
        )
        session.add(learner)
        session.flush()
        attempt = AssessmentAttempt(
            organization_id=str(org.id),
            institution_id=str(inst.id),
            learner_id=str(learner.id),
            state="in_progress",
            trust_mode="synthetic_d15_harness",
            assessment_key="a",
            performance_mode="practice",
            idempotency_key="k",
            content_fingerprint="fp",
            synthetic_harness_only=True,
        )
        session.add(attempt)
        session.commit()

        item = build_two_item_catalog_items()[0]
        score = score_item_response(
            item,
            RecordResponseRequest(
                actor=TrustedActorContext(
                    organization_id=str(org.id),
                    institution_id=str(inst.id),
                    learner_id=str(learner.id),
                ),
                attempt_id=str(attempt.id),
                item_sequence=1,
                response_kind=ResponseKind.SINGLE_CHOICE,
                selected_option_keys=["A"],
            ),
        )
        assert record_diagnostic_events(
            session,
            organization_id=str(org.id),
            institution_id=str(inst.id),
            learner_id=str(learner.id),
            attempt_id=str(attempt.id),
            item=item,
            selected_option_keys=["A"],
            score=score,
        ) == []

        assert apply_mastery_update(
            session,
            organization_id=str(org.id),
            institution_id=str(inst.id),
            learner_id=str(learner.id),
            concept_code="c",
            event=ScoreEvidenceEvent(
                attempt_id=str(attempt.id),
                organization_id=str(org.id),
                learner_id=str(learner.id),
                item_sequence=1,
                verdict=ScoringVerdict.INCORRECT.value,
                marks_awarded=0,
                max_marks=4,
                snapshot_fingerprint="fp",
            ),
        ) is None

        resp, issues = validate_and_store_response(
            session,
            attempt,
            RecordResponseRequest(
                actor=TrustedActorContext(
                    organization_id=str(org.id),
                    institution_id=str(inst.id),
                    learner_id=str(learner.id),
                ),
                attempt_id=str(attempt.id),
                item_sequence=1,
                response_kind=ResponseKind.SINGLE_CHOICE,
                selected_option_keys=["A"],
            ),
            item_model_json=item.model_dump(mode="json"),
        )
        assert resp is None
        assert IssueCode.NOT_READY in issues

        rows, q_issues = read_diagnostic_events(
            session,
            TrustedActorContext(
                organization_id=str(org.id),
                institution_id=str(inst.id),
                learner_id=str(learner.id),
            ),
        )
        assert rows == []
        assert IssueCode.NOT_READY in q_issues

        events = session.scalar(select(func.count()).select_from(ScoreEvidenceEvent))
        assert events == 0

        try:
            finalize_attempt(
                session,
                FinalizeAttemptRequest(
                    actor=TrustedActorContext(
                        organization_id=str(org.id),
                        institution_id=str(inst.id),
                        learner_id=str(learner.id),
                    ),
                    attempt_id=str(attempt.id),
                    idempotency_key="fin",
                    content_binding_fingerprint="fp",
                ),
            )
            raised = False
        except FinalizationError as exc:
            raised = exc.code == IssueCode.NOT_READY
        assert raised

        with pytest.raises(LifecycleBlockedError):
            transition_attempt(session, attempt, AttemptState.ABANDONED)