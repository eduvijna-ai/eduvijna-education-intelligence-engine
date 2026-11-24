from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import (
    CreateAttemptRequest,
    SnapshotItem,
    TrustedActorContext,
)
from app.learner_intelligence.enums import MASTERY_POLICY_VERSION
from app.learner_intelligence.harness import (
    TRUSTED_CATALOG_KEY_TWO_ITEM,
    build_harness_create_request,
    build_two_item_catalog_items,
    compute_harness_attestation,
)
from app.learner_intelligence.snapshot import compute_assessment_fingerprint
from app.models import Institution, Learner, Organization


def seed_synthetic_tenant(session: Session) -> TrustedActorContext:
    if not runtime_learner_db_io_allowed():
        raise RuntimeError("day15_seed_blocked_by_containment")
    org = Organization(code="d15-org", name="D15 Synthetic Org", active=True)
    session.add(org)
    session.flush()
    inst = Institution(
        organization_id=str(org.id),
        code="d15-inst",
        name="D15 Synthetic Institution",
        active=True,
    )
    session.add(inst)
    session.flush()
    learner = Learner(
        institution_id=str(inst.id),
        external_code="d15-learner-1",
        display_name="Synthetic Learner",
        active=True,
    )
    session.add(learner)
    session.flush()
    return TrustedActorContext(
        organization_id=str(org.id),
        institution_id=str(inst.id),
        learner_id=str(learner.id),
    )


def build_two_item_synthetic_assessment() -> list[SnapshotItem]:
    return build_two_item_catalog_items()


def build_harness_attempt_request(
    actor: TrustedActorContext,
    *,
    assessment_key: str,
    idempotency_key: str,
) -> CreateAttemptRequest:
    return build_harness_create_request(
        actor,
        catalog_key=TRUSTED_CATALOG_KEY_TWO_ITEM,
        assessment_key=assessment_key,
        idempotency_key=idempotency_key,
    )


def assessment_content_fingerprint(items: list[SnapshotItem]) -> str:
    return compute_assessment_fingerprint(items)


def forged_harness_attestation_copy() -> str:
    items = build_two_item_catalog_items()
    return compute_harness_attestation(TRUSTED_CATALOG_KEY_TWO_ITEM, items) + "0"


MASTERY_POLICY = MASTERY_POLICY_VERSION