from pathlib import Path

from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.learner_intelligence.contracts import CreateAttemptRequest, TrustedActorContext
from app.learner_intelligence.eligibility import (
    diagnose_pure_catalog_structure,
    evaluate_assessment_eligibility,
)
from app.learner_intelligence.enums import EligibilityTrustMode, EligibilityVerdict, IssueCode
from app.learner_intelligence.fixtures import (
    build_harness_attempt_request,
    build_two_item_synthetic_assessment,
    forged_harness_attestation_copy,
)
from app.learner_intelligence.harness import TRUSTED_CATALOG_KEY_TWO_ITEM
from app.learner_intelligence.service import LearnerIntelligenceService


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        organization_id="org-a",
        institution_id="inst-a",
        learner_id="learner-a",
    )


def test_runtime_eligibility_always_blocked_even_valid_catalog() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k0")
    assert diagnose_pure_catalog_structure(req) == EligibilityVerdict.ELIGIBLE
    assert evaluate_assessment_eligibility(req) == EligibilityVerdict.BLOCKED_UNVERIFIED


def test_forged_attestation_blocked_structural_diagnostic() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k1")
    forged = req.model_copy(update={"harness_attestation": forged_harness_attestation_copy()})
    assert diagnose_pure_catalog_structure(forged) == EligibilityVerdict.BLOCKED_FORGED_APPROVAL
    assert evaluate_assessment_eligibility(forged) == EligibilityVerdict.BLOCKED_UNVERIFIED


def test_contained_ca_pack_blocked() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k2")
    blocked = req.model_copy(update={"exam_pack_code": "ca_foundation"})
    assert diagnose_pure_catalog_structure(blocked) == EligibilityVerdict.BLOCKED_CONTAINMENT


def test_exact_imat_pack_blocked() -> None:
    req = build_harness_attempt_request(_actor(), assessment_key="x", idempotency_key="k-imat")
    blocked = req.model_copy(update={"exam_pack_code": "imat"})
    assert diagnose_pure_catalog_structure(blocked) == EligibilityVerdict.BLOCKED_CONTAINMENT


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
    verdict = diagnose_pure_catalog_structure(req)
    assert verdict in (
        EligibilityVerdict.BLOCKED_FORGED_APPROVAL,
        EligibilityVerdict.BLOCKED_UNVERIFIED,
    )


def _seed_membership(tmp_path: Path) -> tuple[Session, TrustedActorContext]:
    from app.models import Institution, Learner, Organization

    engine = create_database_engine(f"sqlite:///{tmp_path / 'attack.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    org = Organization(code="d15-org", name="D15", active=True)
    session.add(org)
    session.flush()
    inst = Institution(
        organization_id=str(org.id),
        code="d15-inst",
        name="D15",
        active=True,
    )
    session.add(inst)
    session.flush()
    learner = Learner(
        institution_id=str(inst.id),
        external_code="d15-learner",
        display_name="L",
        active=True,
    )
    session.add(learner)
    session.flush()
    actor = TrustedActorContext(
        organization_id=str(org.id),
        institution_id=str(inst.id),
        learner_id=str(learner.id),
    )
    session.commit()
    return session, actor


def test_service_blocks_valid_membership_and_copied_attestation(tmp_path: Path) -> None:
    session, actor = _seed_membership(tmp_path)
    try:
        req = build_harness_attempt_request(actor, assessment_key="t", idempotency_key="t1")
        svc = LearnerIntelligenceService()
        attempt, outcome = svc.create_attempt(session, req)
        assert attempt is None
        assert IssueCode.NOT_READY in outcome.issue_codes
        assert outcome.committed is False
        session.info["d15_harness_authorized"] = True
        session.info["d15_harness_binding_secret"] = "forged"
        attempt2, outcome2 = svc.create_attempt(session, req)
        assert attempt2 is None
        assert IssueCode.NOT_READY in outcome2.issue_codes
    finally:
        session.close()