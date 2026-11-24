from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.learner_intelligence.containment import containment_issue
from app.learner_intelligence.contracts import (
    AttemptOutcome,
    FinalizeAttemptRequest,
    RecordResponseRequest,
    TrustedActorContext,
)
from app.learner_intelligence.enums import AttemptState, EligibilityVerdict, IssueCode, ResponseKind
from app.learner_intelligence.finalization import (
    FinalizationError,
    _recompute_binding_fingerprint,
    _verify_cached_idempotent_outcome,
    _verify_persisted_snapshots,
    finalize_attempt,
)
from app.learner_intelligence.harness import build_two_item_catalog_items
from app.learner_intelligence.history import record_history_observation
from app.learner_intelligence.lifecycle import (
    LifecycleBlockedError,
    abandon_attempt,
    load_snapshot_item,
    mark_responses_final,
    preview_score_for_draft,
    transition_attempt,
    validate_and_store_response,
)
from app.learner_intelligence.memory import append_memory_from_event
from app.learner_intelligence.scoring import score_item_response
from app.models import Institution, Learner, Organization
from app.models.learner_intelligence import AssessmentAttempt, ScoreEvidenceEvent


class _SessionCallCounter:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.scalar_calls = 0
        self.scalars_calls = 0
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.add_calls = 0
        self.get_calls = 0

    def wrap(self) -> Session:
        session = self._session
        orig_scalar = session.scalar
        orig_scalars = session.scalars
        orig_flush = session.flush
        orig_commit = session.commit
        orig_rollback = session.rollback
        orig_add = session.add
        orig_get = session.get

        counter = self

        def scalar(*args: Any, **kwargs: Any) -> Any:
            counter.scalar_calls += 1
            return orig_scalar(*args, **kwargs)

        def scalars(*args: Any, **kwargs: Any) -> Any:
            counter.scalars_calls += 1
            return orig_scalars(*args, **kwargs)

        def flush(*args: Any, **kwargs: Any) -> None:
            counter.flush_calls += 1
            orig_flush(*args, **kwargs)

        def commit(*args: Any, **kwargs: Any) -> None:
            counter.commit_calls += 1
            orig_commit(*args, **kwargs)

        def rollback(*args: Any, **kwargs: Any) -> None:
            counter.rollback_calls += 1
            orig_rollback(*args, **kwargs)

        def add(*args: Any, **kwargs: Any) -> None:
            counter.add_calls += 1
            orig_add(*args, **kwargs)

        def get(*args: Any, **kwargs: Any) -> Any:
            counter.get_calls += 1
            return orig_get(*args, **kwargs)

        session.scalar = scalar  # type: ignore[method-assign]
        session.scalars = scalars  # type: ignore[method-assign]
        session.flush = flush  # type: ignore[method-assign]
        session.commit = commit  # type: ignore[method-assign]
        session.rollback = rollback  # type: ignore[method-assign]
        session.add = add  # type: ignore[method-assign]
        session.get = get  # type: ignore[method-assign]
        return session


@pytest.fixture()
def persisted_attempt(tmp_path: Path) -> tuple[Session, AssessmentAttempt]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'seal.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    org = Organization(code="seal-org", name="Seal", active=True)
    session.add(org)
    session.flush()
    inst = Institution(
        organization_id=str(org.id),
        code="seal-inst",
        name="Seal Inst",
        active=True,
    )
    session.add(inst)
    session.flush()
    learner = Learner(
        institution_id=str(inst.id),
        external_code="seal-learner",
        display_name="Seal Learner",
        active=True,
    )
    session.add(learner)
    session.flush()
    attempt = AssessmentAttempt(
        organization_id=str(org.id),
        institution_id=str(inst.id),
        learner_id=str(learner.id),
        state=AttemptState.CREATED.value,
        trust_mode="synthetic_d15_harness",
        assessment_key="a",
        performance_mode="practice",
        idempotency_key="k",
        content_fingerprint="fp",
        synthetic_harness_only=True,
    )
    session.add(attempt)
    session.commit()
    session.expire_all()
    loaded = session.get(AssessmentAttempt, attempt.id)
    assert loaded is not None
    return session, loaded


def test_lifecycle_helpers_block_before_sql(
    persisted_attempt: tuple[Session, AssessmentAttempt],
) -> None:
    session, attempt = persisted_attempt
    counter = _SessionCallCounter(session)
    counter.wrap()
    state_before = attempt.state

    with pytest.raises(LifecycleBlockedError) as exc:
        transition_attempt(session, attempt, AttemptState.IN_PROGRESS)
    assert exc.value.code == containment_issue()

    with pytest.raises(LifecycleBlockedError):
        load_snapshot_item(session, str(attempt.id), 1)

    item = build_two_item_catalog_items()[0]
    actor = TrustedActorContext(
        organization_id=attempt.organization_id,
        institution_id=attempt.institution_id,
        learner_id=attempt.learner_id,
    )
    with pytest.raises(LifecycleBlockedError):
        preview_score_for_draft(
            session,
            str(attempt.id),
            RecordResponseRequest(
                actor=actor,
                attempt_id=str(attempt.id),
                item_sequence=1,
                response_kind=ResponseKind.SINGLE_CHOICE,
                selected_option_keys=["A"],
            ),
            item,
        )

    with pytest.raises(LifecycleBlockedError):
        mark_responses_final(session, str(attempt.id))

    with pytest.raises(LifecycleBlockedError):
        abandon_attempt(session, attempt)

    resp, issues = validate_and_store_response(
        session,
        attempt,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["A"],
        ),
        item_model_json=item.model_dump(mode="json"),
    )
    assert resp is None
    assert IssueCode.NOT_READY in issues

    assert counter.scalar_calls == 0
    assert counter.scalars_calls == 0
    assert counter.add_calls == 0
    assert counter.flush_calls == 0
    assert attempt.state == state_before


def test_finalization_helpers_block_before_sql(
    persisted_attempt: tuple[Session, AssessmentAttempt],
) -> None:
    session, attempt = persisted_attempt
    counter = _SessionCallCounter(session)
    counter.wrap()
    actor = TrustedActorContext(
        organization_id=attempt.organization_id,
        institution_id=attempt.institution_id,
        learner_id=attempt.learner_id,
    )

    with pytest.raises(FinalizationError) as exc:
        finalize_attempt(
            session,
            FinalizeAttemptRequest(
                actor=actor,
                attempt_id=str(attempt.id),
                idempotency_key="fin",
                content_binding_fingerprint="fp",
            ),
        )
    assert exc.value.code == containment_issue()

    with pytest.raises(FinalizationError):
        _verify_persisted_snapshots(session, str(attempt.id))

    with pytest.raises(FinalizationError):
        _recompute_binding_fingerprint(session, str(attempt.id))

    with pytest.raises(FinalizationError):
        _verify_cached_idempotent_outcome(
            session,
            attempt=attempt,
            cached=AttemptOutcome(
                attempt_id=str(attempt.id),
                state=AttemptState.FINALIZED,
                eligibility_verdict=EligibilityVerdict.BLOCKED_UNVERIFIED,
            ),
            binding="fp",
            snapshot_count=1,
        )

    assert counter.scalar_calls == 0
    assert counter.scalars_calls == 0


def test_history_memory_return_none_without_orm_or_sql(
    persisted_attempt: tuple[Session, AssessmentAttempt],
) -> None:
    session, attempt = persisted_attempt
    item = build_two_item_catalog_items()[0]
    score = score_item_response(
        item,
        RecordResponseRequest(
            actor=TrustedActorContext(
                organization_id=attempt.organization_id,
                institution_id=attempt.institution_id,
                learner_id=attempt.learner_id,
            ),
            attempt_id=str(attempt.id),
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["A"],
        ),
    )
    event = ScoreEvidenceEvent(
        attempt_id=str(attempt.id),
        organization_id=attempt.organization_id,
        learner_id=attempt.learner_id,
        item_sequence=1,
        verdict="incorrect",
        marks_awarded=0,
        max_marks=4,
        snapshot_fingerprint="fp",
    )
    counter = _SessionCallCounter(session)
    counter.wrap()

    hist = record_history_observation(
        session,
        organization_id=attempt.organization_id,
        learner_id=attempt.learner_id,
        attempt_id=str(attempt.id),
        question_id=item.question_id,
        item_sequence=1,
        source_version="v",
        score=score,
    )
    mem = append_memory_from_event(
        session,
        organization_id=attempt.organization_id,
        learner_id=attempt.learner_id,
        memory_key="k",
        event=event,
        payload={"x": 1},
    )
    assert hist is None
    assert mem is None
    assert counter.scalars_calls == 0
    assert counter.add_calls == 0


def test_blocked_calls_preserve_pending_caller_work(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'pending-seal.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Organization(code="pending", name="P", active=False))
    session.flush()
    counter = _SessionCallCounter(session)
    counter.wrap()
    attempt = AssessmentAttempt(
        organization_id="o",
        institution_id="i",
        learner_id="l",
        state=AttemptState.CREATED.value,
        trust_mode="synthetic_d15_harness",
        assessment_key="a",
        performance_mode="practice",
        idempotency_key="k",
        content_fingerprint="fp",
        synthetic_harness_only=True,
    )
    with pytest.raises(LifecycleBlockedError):
        transition_attempt(session, attempt, AttemptState.IN_PROGRESS)
    assert counter.flush_calls == 0
    session.rollback()
    count = session.scalar(select(func.count()).select_from(Organization))
    assert count == 0
    session.close()