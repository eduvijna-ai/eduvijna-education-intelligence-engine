from __future__ import annotations

from app.ca_imat_eapcet.containment import ISSUANCE_DISABLED
from app.learner_intelligence.containment import PRODUCTION_ASSESSMENT_ELIGIBILITY
from app.learner_intelligence.contracts import CreateAttemptRequest
from app.learner_intelligence.enums import EligibilityTrustMode, EligibilityVerdict
from app.learner_intelligence.harness import (
    is_blocked_exam_pack,
    verify_harness_attestation,
)
from app.learner_intelligence.snapshot import (
    compute_assessment_fingerprint,
    compute_item_fingerprint,
    validate_items_structure,
)


def evaluate_assessment_eligibility(request: CreateAttemptRequest) -> EligibilityVerdict:
    """Runtime assessment gate — unconditionally blocked under containment."""

    _ = request
    return EligibilityVerdict.BLOCKED_UNVERIFIED


def diagnose_pure_catalog_structure(request: CreateAttemptRequest) -> EligibilityVerdict:
    """Non-authoritative structural diagnostic only; not runtime eligibility."""

    if request.trust_mode != EligibilityTrustMode.SYNTHETIC_D15_HARNESS:
        return EligibilityVerdict.BLOCKED_UNVERIFIED
    if ISSUANCE_DISABLED:
        pass
    if not request.catalog_key or not request.harness_attestation:
        return EligibilityVerdict.BLOCKED_UNVERIFIED
    if is_blocked_exam_pack(request.exam_pack_code):
        return EligibilityVerdict.BLOCKED_CONTAINMENT
    if not request.items:
        return EligibilityVerdict.BLOCKED_SCOPE
    structural = validate_items_structure(request.items)
    if structural is not None:
        return EligibilityVerdict.BLOCKED_SCOPE
    for item in request.items:
        if item.content_fingerprint != compute_item_fingerprint(item):
            return EligibilityVerdict.BLOCKED_UNVERIFIED
    if not verify_harness_attestation(
        request.catalog_key, request.items, request.harness_attestation
    ):
        return EligibilityVerdict.BLOCKED_FORGED_APPROVAL
    if request.exam_version_id and request.exam_pack_code:
        return EligibilityVerdict.BLOCKED_UNVERIFIED
    _ = compute_assessment_fingerprint(request.items)
    return EligibilityVerdict.ELIGIBLE


def production_assessment_always_blocked() -> bool:
    return not PRODUCTION_ASSESSMENT_ELIGIBILITY