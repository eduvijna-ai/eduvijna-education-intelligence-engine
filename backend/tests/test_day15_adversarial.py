from pathlib import Path

from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.learner_intelligence.contracts import CreateAttemptRequest, TrustedActorContext
from app.learner_intelligence.eligibility import evaluate_assessment_eligibility
from app.learner_intelligence.enums import EligibilityTrustMode, EligibilityVerdict, IssueCode
from app.learner_intelligence.fixtures import (
    build_harness_attempt_request,
    build_two_item_synthetic_assessment,
    forged_harness_attestation_copy,
    seed_synthetic_tenant,
)
from app.learner_intelligence.harness import TRUSTED_CATALOG_KEY_TWO_ITEM
from app.learner_intelligence.harness_runtime import (
    ephemeral_file_harness,
    isolated_harness_session,
)
from app.learner_intelligence.service import LearnerIntelligenceService


def _unauthorized_session(tmp_path: Path) -> tuple[Session, TrustedActorContext]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'd15-plain.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    actor = seed_synthetic_tenant(session)
    session.commit()
    return session, actor


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        organization_id="org-a",
        institution_id="inst-a",
        learner_id="learner-a",
    )


def test_forged_attestation_blocked() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k1")
    forged = req.model_copy(update={"harness_attestation": forged_harness_attestation_copy()})
    assert evaluate_assessment_eligibility(forged) == EligibilityVerdict.BLOCKED_FORGED_APPROVAL


def test_contained_ca_pack_blocked() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k2")
    blocked = req.model_copy(update={"exam_pack_code": "ca_foundation"})
    assert evaluate_assessment_eligibility(blocked) == EligibilityVerdict.BLOCKED_CONTAINMENT


def test_exact_imat_pack_blocked() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k-imat")
    blocked = req.model_copy(update={"exam_pack_code": "imat"})
    assert evaluate_assessment_eligibility(blocked) == EligibilityVerdict.BLOCKED_CONTAINMENT


def test_arbitrary_items_without_catalog_blocked() -> None:
    items = build_two_item_synthetic_assessment()
    items[0] = items[0].model_copy(update={"stem_text": "tampered"})
    req = CreateAttemptRequest(
        actor=_actor(),
        trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
        assessment_key="x",
        idempotency_key="k3",
        items=items,
        catalog_key=TRUSTED_CATALOG_KEY_TWO_ITEM,
        harness_attestation="deadbeef" * 8,
    )
    verdict = evaluate_assessment_eligibility(req)
    assert verdict in (
        EligibilityVerdict.BLOCKED_FORGED_APPROVAL,
        EligibilityVerdict.BLOCKED_UNVERIFIED,
    )


def test_ordinary_session_rejects_create(tmp_path: Path) -> None:
    session, actor = _unauthorized_session(tmp_path)
    try:
        svc = LearnerIntelligenceService()
        attempt, outcome = svc.create_attempt(
            session,
            build_harness_attempt_request(actor, assessment_key="t", idempotency_key="t0"),
        )
        assert attempt is None
        assert IssueCode.NOT_ELIGIBLE in outcome.issue_codes
    finally:
        session.close()


def test_cross_tenant_learner_view_blocked(tmp_path: Path) -> None:
    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as (session, _binding, actor):
        svc = LearnerIntelligenceService()
        attempt, _ = svc.create_attempt(
            session,
            build_harness_attempt_request(actor, assessment_key="t", idempotency_key="t1"),
        )
        assert attempt is not None
        other = TrustedActorContext(
            organization_id=actor.organization_id,
            institution_id=actor.institution_id,
            learner_id="foreign-learner",
        )
        _, issues = svc.learner_view_items(session, other, str(attempt.id))
        assert IssueCode.TENANT_MISMATCH in issues or IssueCode.OUT_OF_SCOPE in issues