from app.learner_intelligence.contracts import CreateAttemptRequest, TrustedActorContext
from app.learner_intelligence.eligibility import evaluate_assessment_eligibility
from app.learner_intelligence.enums import EligibilityTrustMode, EligibilityVerdict
from app.learner_intelligence.fixtures import build_two_item_synthetic_assessment
from app.learner_intelligence.privacy import assert_no_cross_tenant


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        organization_id="org-a",
        institution_id="inst-a",
        learner_id="learner-a",
    )


def test_forged_approval_blocked() -> None:
    req = CreateAttemptRequest(
        actor=_actor(),
        trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
        assessment_key="x",
        idempotency_key="k1",
        items=build_two_item_synthetic_assessment(),
        synthetic_harness_proof="FORGED_APPROVED_FLAG",
    )
    assert evaluate_assessment_eligibility(req) == EligibilityVerdict.BLOCKED_FORGED_APPROVAL


def test_day11_pack_blocked() -> None:
    req = CreateAttemptRequest(
        actor=_actor(),
        trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
        assessment_key="x",
        idempotency_key="k2",
        items=build_two_item_synthetic_assessment(),
        synthetic_harness_proof="synthetic_fixture_v1",
        exam_pack_code="day11_jee",
    )
    assert evaluate_assessment_eligibility(req) == EligibilityVerdict.BLOCKED_UNVERIFIED


def test_cross_tenant_mismatch() -> None:
    assert not assert_no_cross_tenant(
        expected_organization_id="org-a",
        expected_institution_id="inst-a",
        actual_organization_id="org-b",
        actual_institution_id="inst-b",
    )