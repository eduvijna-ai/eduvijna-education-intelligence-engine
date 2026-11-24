from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.learner_intelligence.enums import MasteryLevel
from app.learner_intelligence.fixtures import (
    build_harness_attempt_request,
    seed_synthetic_tenant,
)
from app.learner_intelligence.mastery import compute_mastery_from_events
from app.learner_intelligence.scope_ledger import load_repo_scope_counts
from app.models.learner_intelligence import ScoreEvidenceEvent


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'd15-trust.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_scope_ledger_unique_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] >= 1


def test_mastery_cold_start_unknown() -> None:
    snap = compute_mastery_from_events(
        [],
        concept_code="arithmetic.addition",
        organization_id="o",
        learner_id="l",
    )
    assert snap.level == MasteryLevel.UNKNOWN


def test_alembic_upgrade_head_sqlite(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "alembic.db"
    cfg = Config("/agent/repos/eduvijna-education-intelligence-engine/backend/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    cfg.set_main_option("script_location", "migrations")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "20261124_0021")
    command.upgrade(cfg, "20261124_0022")


def test_harness_create_request_is_self_attested(tmp_path: Path) -> None:
    session = _session(tmp_path)
    actor = seed_synthetic_tenant(session)
    session.commit()
    req = build_harness_attempt_request(actor, assessment_key="hk", idempotency_key="hk1")
    assert req.harness_attestation
    assert req.catalog_key
    session.close()


def test_score_events_scoped_to_org(tmp_path: Path) -> None:
    from app.learner_intelligence.contracts import FinalizeAttemptRequest, RecordResponseRequest
    from app.learner_intelligence.enums import AttemptState, ResponseKind
    from app.learner_intelligence.fixtures import assessment_content_fingerprint
    from app.learner_intelligence.service import LearnerIntelligenceService

    session = _session(tmp_path)
    actor = seed_synthetic_tenant(session)
    session.commit()
    create_req = build_harness_attempt_request(actor, assessment_key="s", idempotency_key="s1")
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
    svc.record_response(
        session,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=2,
            response_kind=ResponseKind.NUMERIC,
            numeric_value="7",
        ),
    )
    fin = svc.finalize(
        session,
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="f1",
            content_binding_fingerprint=fp,
        ),
    )
    assert fin.state == AttemptState.FINALIZED
    count = session.scalar(
        select(func.count()).select_from(ScoreEvidenceEvent).where(
            ScoreEvidenceEvent.organization_id == actor.organization_id
        )
    )
    assert count == 2
    session.close()