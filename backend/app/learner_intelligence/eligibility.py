from __future__ import annotations

from app.ca_imat_eapcet.containment import ISSUANCE_DISABLED
from app.learner_intelligence.contracts import CreateAttemptRequest
from app.learner_intelligence.enums import EligibilityTrustMode, EligibilityVerdict


def evaluate_assessment_eligibility(request: CreateAttemptRequest) -> EligibilityVerdict:
    """D15-05: fail closed; APPROVED flags and Day14 production paths are insufficient."""

    proof = (request.synthetic_harness_proof or "").strip()
    if request.trust_mode != EligibilityTrustMode.SYNTHETIC_D15_HARNESS:
        return EligibilityVerdict.BLOCKED_UNVERIFIED
    if ISSUANCE_DISABLED and request.trust_mode != EligibilityTrustMode.SYNTHETIC_D15_HARNESS:
        return EligibilityVerdict.BLOCKED_CONTAINMENT
    if proof == "FORGED_APPROVED_FLAG":
        return EligibilityVerdict.BLOCKED_FORGED_APPROVAL
    if not request.items:
        return EligibilityVerdict.BLOCKED_SCOPE
    if request.exam_pack_code and request.exam_pack_code.startswith("day11_"):
        return EligibilityVerdict.BLOCKED_UNVERIFIED
    if proof not in ("synthetic_fixture_v1", "day15_verify_harness"):
        return EligibilityVerdict.BLOCKED_UNVERIFIED
    for item in request.items:
        if not item.source_version or not item.content_fingerprint:
            return EligibilityVerdict.BLOCKED_UNVERIFIED
    return EligibilityVerdict.ELIGIBLE