from pathlib import Path

from sqlalchemy import func, select

from app.learner_intelligence.enums import MasteryLevel
from app.learner_intelligence.fixtures import build_harness_attempt_request
from app.learner_intelligence.harness_runtime import (
    ephemeral_file_harness,
    isolated_harness_session,
)
from app.learner_intelligence.mastery import compute_mastery_from_events
from app.learner_intelligence.scope_ledger import load_repo_scope_counts
from app.models.learner_intelligence import ScoreEvidenceEvent


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


def test_mastery_blank_excluded_from_support() -> None:
    from app.learner_intelligence.enums import ScoringVerdict
    from app.models.learner_intelligence import ScoreEvidenceEvent as Event

    events = [
        Event(
            organization_id="o",
            learner_id="l",
            attempt_id="a",
            item_sequence=1,
            verdict=ScoringVerdict.BLANK.value,
            marks_awarded=0,
            max_marks=4,
            snapshot_fingerprint="x",
            concept_codes_json=["arithmetic.addition"],
        )
    ]
    snap = compute_mastery_from_events(
        events,
        concept_code="arithmetic.addition",
        organization_id="o",
        learner_id="l",
    )
    assert snap.level == MasteryLevel.UNKNOWN


def test_alembic_upgrade_head_sqlite(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[1]
    db = tmp_path / "alembic.db"
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    cfg.set_main_option("script_location", str(backend_root / "migrations"))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "20261124_0021")
    command.upgrade(cfg, "20261124_0022")


def test_harness_create_request_is_self_attested(tmp_path: Path) -> None:
    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as (_session, _binding, actor):
        req = build_harness_attempt_request(actor, assessment_key="hk", idempotency_key="hk1")
        assert req.harness_attestation
        assert req.catalog_key


def test_score_events_scoped_to_org(tmp_path: Path) -> None:
    from app.learner_intelligence.contracts import FinalizeAttemptRequest, RecordResponseRequest
    from app.learner_intelligence.enums import AttemptState, ResponseKind
    from app.learner_intelligence.fixtures import assessment_content_fingerprint
    from app.learner_intelligence.service import LearnerIntelligenceService

    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as (session, _binding, actor):
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